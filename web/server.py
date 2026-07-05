#!/usr/bin/env python3
"""Локальный бэкенд дашборда «Консоль обзвона».

Отдаёт статику (web/) и мини-API:
  POST /api/reveal  {hash}  — открыть commercial_realty.xlsx на строке объекта
  POST /api/save    {hash}  — сохранить полную веб-версию объявления (текст+фото) офлайн
  POST /api/update          — обновить базу (collect_realty.py + ре-экспорт) в фоне
  GET  /api/update/status   — статус фонового обновления (лог, флаг running)
  POST /api/update/stop     — остановить обновление

Только localhost. Запуск: ./bin/python web/server.py  (зовётся из Дашборд.command)
"""
import contextlib
import html
import json
import os
import re
import socket
import socketserver
import subprocess
import sys
import threading
import time
import math
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

import fetch_ad  # web/ в sys.path, см. main()
from phones import normalize_phone  # общий канон телефонов

WEB_DIR = Path(__file__).resolve().parent
ROOT = WEB_DIR.parent
DATA_JS = WEB_DIR / "data.js"
SAVED_DIR = WEB_DIR / "saved"
PHOTOS_CACHE_DIR = WEB_DIR / "photos_cache"   # локальный кэш фото (см. /img ниже)
MAIN_XLSX = ROOT / "commercial_realty.xlsx"
START_PORT = int(os.environ.get("PORT") or 8765)   # preview/тест задаёт PORT; иначе дефолт
SHEETS = {"Продажа", "Аренда", "Аукционы"}  # белый список листов для AppleScript
KUFAR_PHONE_LIMIT = 70   # сколько телефонов kufar добирать за одно «Обновить базу».
                         # ⚠ kufar придушивает ~после 25 раскрытий/сессию (даже залогиненным):
                         # выше этого часть запросов уйдёт впустую (no_response) и можно
                         # подставить аккаунт под бан. Денис поднял 20→70 осознанно (20.06);
                         # вернуть к ~20, если kufar начнёт банить/массово отдавать no_response.

# ---- индекс объектов по хэшу (из data.js) ----
INDEX = {}


def load_index():
    INDEX.clear()
    if not DATA_JS.exists():
        return
    txt = DATA_JS.read_text(encoding="utf-8")
    m = re.search(r"window\.LISTINGS=(\[.*\]);", txt, re.S)
    if not m:
        return
    for it in json.loads(m.group(1)):
        if it.get("hash"):
            INDEX[it["hash"]] = it


# ---- фоновое обновление базы ----
JOB = {"running": False, "started": "", "finished": "", "rc": None, "log": ""}
_proc = None


def _stream(cmd):
    """Запустить cmd, лить stdout в JOB['log'] построчно. Вернуть returncode."""
    global _proc
    _proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in _proc.stdout:
        JOB["log"] = (JOB["log"] + line)[-8000:]
    _proc.wait()
    return _proc.returncode


def _update_steps(target, py):
    """Список (заголовок, команда) для target. 'all' = полный прогон всех источников.
    Гео-источники (domovita/edc) и телефоны kufar/belretail сами пропустятся, если IP
    не белорусский — под VPN просто соберут 0, остальное не ломают.

    Правило «свежие первыми» (05.07.2026): СНАЧАЛА весь сбор свежих объявлений
    (realty/geo/auctions/banks), ПОТОМ доборы телефонов (kufar/belretail) — чтобы
    дефицитная дневная квота раскрытий уходила на максимально свежую базу. Доборы
    сами берут свежие строки первыми (kufar_phones.collect_targets идёт с конца)."""
    collect, phones = [], []
    if target in ("all", "realty"):
        collect.append(("Сбор объявлений (realt/megapolis/kufar/gohome/byrealty)",
                        [py, "-u", "collect_realty.py"]))
        # --chrome-cookies: kufar спрятал телефон за логин, берём сессию из Chrome
        phones.append((f"Добор телефонов kufar (до {KUFAR_PHONE_LIMIT}; нужен бел. IP)",
                       [py, "-u", "kufar_phones.py", "--limit", str(KUFAR_PHONE_LIMIT), "--chrome-cookies"]))
    if target in ("all", "geo"):
        collect.append(("Гео-источники domovita + edc (нужен бел. IP — VPN выключен)",
                        [py, "-u", "collect_geo.py"]))
    if target in ("all", "auctions"):
        collect.append(("Сбор аукционов (10 площадок)", [py, "-u", "collect_auctions.py"]))
    if target in ("all", "banks"):
        collect.append(("Недвижимость банков", [py, "-u", "collect_banks.py"]))
        phones.append(("Телефоны компаний belretail (нужен бел. IP)", [py, "-u", "belretail_phones.py"]))
    return collect + phones           # весь сбор свежих → потом доборы телефонов


def _run_update(target="all"):
    global _proc
    py = sys.executable
    warn = ""
    if (ROOT / "~$commercial_realty.xlsx").exists():
        warn = ("⚠ commercial_realty.xlsx сейчас ОТКРЫТ в Excel — запись может не пройти.\n"
                "  Закройте файл в Excel и запустите обновление снова.\n\n")
    steps = _update_steps(target, py)
    n = len(steps)
    JOB.update(running=True, started=datetime.now().strftime("%H:%M:%S"),
               finished="", rc=None, log=warn + f"Обновление: {n} шагов сбора + ре-экспорт.\n")
    rc = 0
    try:
        for i, (label, cmd) in enumerate(steps, 1):
            JOB["log"] += f"\n[{i}/{n}] {label}…\n"
            step_rc = _stream(cmd)
            rc = step_rc or rc  # запомним последний ненулевой код (для статуса)
        JOB["log"] += "\n[ре-экспорт] Обновление данных дашборда…\n"
        ex = subprocess.run([py, "web/export_data.py"], cwd=str(ROOT),
                            capture_output=True, text=True)
        JOB["log"] = (JOB["log"] + ex.stdout + ex.stderr)[-8000:]
        load_index()
        # прогрев фото-кэша: докачиваем фото новых объектов, чтобы карточки были
        # сразу с фото (идемпотентно — уже скачанное пропускается; --limit держит шаг
        # коротким на инкременте). Полный первичный прогрев — web/prefetch_photos.py.
        JOB["log"] += "\n[+] Прогрев фото-кэша (новые объекты)…\n"
        pf = subprocess.run([py, "web/prefetch_photos.py", "--limit", "2000"],
                            cwd=str(ROOT), capture_output=True, text=True)
        JOB["log"] = (JOB["log"] + pf.stdout[-1200:])[-8000:]
        JOB.update(rc=rc)
        JOB["log"] += "\n✅ Готово. Обновите страницу.\n"
    except Exception as e:  # noqa: BLE001
        JOB["log"] += f"\nОшибка: {type(e).__name__}: {e}\n"
        JOB.update(rc=-1)
    finally:
        JOB.update(running=False, finished=datetime.now().strftime("%H:%M:%S"))
        _proc = None


# ---- сохранение полной веб-версии объявления ----
def _download(url, dest, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": fetch_ad.UA,
                                               "Referer": ""})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        dest.write_bytes(r.read())


PHONE_RE = re.compile(
    r"(?:\+?375[\s\-]?\(?\d{2}\)?|8[\s\-]?\(?0\d{2}\)?)[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")


def phones_from_text(text):
    """Телефоны прямо в тексте объявления (kufar так делает в ~7% случаев).
    PHONE_RE ловит шейп номера в свободном тексте, normalize_phone (общий канон)
    приводит к +375… и валидирует длину; дедуп с сохранением порядка."""
    out = []
    for m in PHONE_RE.findall(text or ""):
        canon = normalize_phone(m)
        if canon and canon not in out:
            out.append(canon)
    return out[:3]


def list_saved():
    if not SAVED_DIR.exists():
        return []
    return sorted(d.name for d in SAVED_DIR.iterdir()
                  if (d / "index.html").exists())


# ---- превью-фото по требованию (realt не отдаёт фото в листинге) ----
PHOTO_CACHE_F = WEB_DIR / "photo_cache.json"
PHOTO_SEM = threading.Semaphore(3)   # не душим realt параллельными запросами
_photo_lock = threading.Lock()
PHOTO_CACHE = {}


def load_photo_cache():
    with contextlib.suppress(Exception):
        PHOTO_CACHE.update(json.loads(PHOTO_CACHE_F.read_text(encoding="utf-8")))


def api_photo(hsh):
    it = _lookup(hsh)
    if not it:
        return {"ok": False, "error": "объект не найден"}
    if it.get("photo"):
        return {"ok": True, "photo": it["photo"]}
    cached = PHOTO_CACHE.get(hsh)
    if cached is not None:                      # "" = уже пробовали, фото нет
        return {"ok": bool(cached), "photo": cached}
    url = it.get("url", "")
    if not url:
        return {"ok": False, "error": "нет ссылки"}
    with PHOTO_SEM:
        if hsh in PHOTO_CACHE:                  # другой поток уже сходил
            c = PHOTO_CACHE[hsh]
            return {"ok": bool(c), "photo": c}
        photo = fetch_ad.first_og_image(url)
    with _photo_lock:
        PHOTO_CACHE[hsh] = photo
        with contextlib.suppress(Exception):
            PHOTO_CACHE_F.write_text(
                json.dumps(PHOTO_CACHE, ensure_ascii=False), encoding="utf-8")
    return {"ok": bool(photo), "photo": photo}


def _lookup(hsh):
    it = INDEX.get(hsh)
    if not it:           # data.js могли перевыгрузить после старта — перечитаем
        load_index()
        it = INDEX.get(hsh)
    return it


# ---- локальный фото-кэш: дашборд грузит фото с localhost, а не с бел-CDN напрямую ----
# Браузерная пачка из ~48 параллельных запросов к rms.kufar.by под VPN (иностранный IP)
# стопорится — серые карточки и недогруз («обрезанное»). Сервер тянет ПОЛНОразмер
# ПОСЛЕДОВАТЕЛЬНО (семафор) — это проверено рабочим под тем же VPN — и кладёт на диск;
# дальше отдаём фото с диска мгновенно, независимо от IP/VPN.
FETCH_SEM = threading.Semaphore(3)        # не душить источник параллельной пачкой
_IMG_CT = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}


def _cached_photo(hsh):
    for ext in (".jpg", ".png", ".webp"):
        p = PHOTOS_CACHE_DIR / (hsh + ext)
        if p.exists():
            return p
    return None


def _photo_urls(it):
    """URL-кандидаты фото по приоритету. Сначала готовый photo (kufar: миниатюра→gallery),
    затем og:image деталки — он живой даже когда сохранённый photo протух (megapolis чистит
    свой кэш-ресайз assets/cache/...-600x400 → 404; og отдаёт оригинал assets/images/...)."""
    out = []
    u = it.get("photo") or ""
    if u:
        out.append(u.replace("/v1/list_thumbs_2x/", "/v1/gallery/"))
    url = it.get("url") or ""
    if url:
        with contextlib.suppress(Exception):
            og = fetch_ad.first_og_image(url)
            if og and og not in out:
                out.append(og)
    return out


def fetch_photo(hsh):
    """Скачать фото объекта в кэш (если ещё нет). Path при успехе, None — фото нет."""
    if not hsh:
        return None
    p = _cached_photo(hsh)
    if p:
        return p
    none_mark = PHOTOS_CACHE_DIR / (hsh + ".none")
    if none_mark.exists():        # уже знаем, что фото нет — источник повторно не дёргаем
        return None
    it = _lookup(hsh)
    if not it:
        return None
    with FETCH_SEM:               # последовательно — иначе источник стопорит пачку
        p = _cached_photo(hsh)    # другой поток мог успеть, пока ждали семафор
        if p:
            return p
        data = b""
        for src in _photo_urls(it):   # photo-поле, при промахе — og:image деталки
            req = urllib.request.Request(
                src, headers={"User-Agent": fetch_ad.UA, "Referer": ""})
            with contextlib.suppress(Exception):
                with urllib.request.urlopen(req, timeout=15) as r:
                    data = r.read()
            if len(data) >= 200:
                break
        PHOTOS_CACHE_DIR.mkdir(exist_ok=True)
        if len(data) < 200:       # пусто/битьё — помечаем «нет фото», чтобы не дёргать снова
            none_mark.touch()
            return None
        ext = (".png" if data[:8] == b"\x89PNG\r\n\x1a\n"
               else ".webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP"
               else ".jpg")
        dest = PHOTOS_CACHE_DIR / (hsh + ext)
        dest.write_bytes(data)
        return dest


def save_ad(hsh):
    it = _lookup(hsh)
    if not it:
        return {"ok": False, "error": "объект не найден (обновите данные)"}
    url = it.get("url", "")
    if not url:
        return {"ok": False, "error": "у объекта нет ссылки"}
    ad = fetch_ad.fetch_full_ad(url)
    folder = SAVED_DIR / hsh
    photos_dir = folder / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    # фото параллельно (последовательно — минуты; Safari обрывает fetch ~60с)
    def grab(args):
        i, pu = args
        ext = ".jpg"
        mt = re.search(r"\.(jpe?g|png|webp)(?:$|\?)", pu, re.I)
        if mt:
            ext = "." + mt.group(1).lower()
        fn = photos_dir / f"{i:02d}{ext}"
        try:
            _download(pu, fn)
            return f"photos/{fn.name}"
        except Exception:  # noqa: BLE001 — фото может не отдаться, продолжаем
            return None

    urls = list(enumerate(ad.get("photos", [])[:30]))
    with ThreadPoolExecutor(max_workers=6) as ex:
        saved_photos = [p for p in ex.map(grab, urls) if p]
    # текст: предпочитаем полный из деталки, иначе сниппет из строки
    text = ad.get("text") or it.get("desc") or ""
    title = ad.get("title") or it.get("type") or "Объявление"
    # телефон: из строки таблицы, иначе пробуем из текста объявления
    phone = it.get("phone") or ", ".join(phones_from_text(text))
    _write_offline_html(folder, it, title, text, saved_photos, url, ad, phone)
    return {"ok": ad.get("ok", False), "error": ad.get("error", ""),
            "hash": hsh, "url": f"/saved/{hsh}/index.html",
            "photos": len(saved_photos), "textLen": len(text)}


def _write_offline_html(folder, it, title, text, photos, src_url, ad, phone=""):
    e = html.escape
    deal = "Продажа" if it.get("deal") == "sale" else "Аренда"
    if phone:
        phone_cell = e(phone)
        if not it.get("phone"):
            phone_cell += ' <span class="warn">(найден в тексте объявления)</span>'
    else:
        why = " (kufar скрывает за капчей)" if "kufar" in (it.get("source") or "") else ""
        phone_cell = f'<span class="warn">нет в объявлении{e(why)}</span>'
    fields = [
        ("Тип", it.get("type")), ("Сделка", deal), ("Цена", it.get("price")),
        ("Площадь", f"{it.get('area')} м²" if it.get("area") else ""),
        ("Этаж", it.get("floor")), ("Город", it.get("city")),
        ("Адрес", it.get("addr")),
        ("Источник", it.get("source")), ("Дата публикации", it.get("date")),
    ]
    rows = f"<tr><th>Телефон</th><td>{phone_cell}</td></tr>" + "".join(
        f"<tr><th>{e(k)}</th><td>{e(str(v))}</td></tr>" for k, v in fields if v)
    gallery = "".join(
        f'<a href="{e(p)}" target="_blank"><img src="{e(p)}" loading="lazy" alt=""></a>'
        for p in photos)
    paras = "".join(f"<p>{e(par.strip())}</p>" for par in re.split(r"\n{2,}|\r?\n", text) if par.strip())
    coords = it.get("coords")
    map_link = (f'<a href="https://www.openstreetmap.org/?mlat={coords[0]}&mlon={coords[1]}'
                f'#map=18/{coords[0]}/{coords[1]}" target="_blank">Карта</a>') if coords else ""
    note = "" if ad.get("ok") else f'<p class="warn">⚠ Полный текст/фото подтянуть не удалось ({e(ad.get("error",""))}). Сохранено из таблицы.</p>'
    doc = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>
:root{{color-scheme:light dark}}
body{{font:15px/1.55 -apple-system,system-ui,sans-serif;max-width:900px;margin:0 auto;padding:24px;color:#1a1a22;background:#fff}}
@media(prefers-color-scheme:dark){{body{{background:#16181d;color:#e8e8ee}}th{{color:#9aa}}}}
h1{{font-size:24px;letter-spacing:-.02em;margin:0 0 4px}}
.src{{color:#888;font-size:13px;margin-bottom:18px}}
.gallery{{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:8px;margin:18px 0}}
.gallery img{{width:100%;height:150px;object-fit:cover;border-radius:8px;display:block}}
table{{border-collapse:collapse;margin:8px 0 20px;width:100%}}
th,td{{text-align:left;padding:6px 12px;border-bottom:1px solid #e6e6ee;vertical-align:top}}
th{{width:160px;color:#667;font-weight:600}}
p{{margin:0 0 12px}}.warn{{color:#b4690e}}
a.src-btn{{display:inline-block;margin-top:8px;color:#3b5bdb}}
</style></head><body>
<h1>{e(title)}</h1>
<div class="src">{e(it.get("source",""))} · сохранено {datetime.now().strftime("%d.%m.%Y %H:%M")} · {map_link}</div>
{note}
<div class="gallery">{gallery or "<i>фото нет</i>"}</div>
<table>{rows}</table>
<h2>Описание</h2>
{paras or "<p><i>текст недоступен</i></p>"}
<a class="src-btn" href="{e(src_url)}" target="_blank" rel="noopener">Открыть оригинал ↗</a>
</body></html>"""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "index.html").write_text(doc, encoding="utf-8")


# ---- открыть объект в Excel ----
def reveal(hsh):
    it = _lookup(hsh)
    if not it:
        return {"ok": False, "error": "объект не найден"}
    sheet, row = it.get("sheet"), it.get("row")
    if sheet not in SHEETS or not isinstance(row, int):
        return {"ok": False, "error": "нет координат строки"}
    if not MAIN_XLSX.exists():
        return {"ok": False, "error": "нет commercial_realty.xlsx"}
    # Если книга уже открыта — активируем её (повторный open показал бы диалоги).
    # Выделяем ВСЮ строку объявления и прокручиваем окно к ней (шапка заморожена
    # на 2 строках, поэтому scroll row = сама строка даёт её сразу под шапкой).
    scroll_to = max(1, row - 1)
    script = (
        f'tell application "Microsoft Excel"\n'
        f'  activate\n'
        f'  try\n'
        f'    activate object workbook "{MAIN_XLSX.name}"\n'
        f'  on error\n'
        f'    open POSIX file "{MAIN_XLSX}"\n'
        f'  end try\n'
        f'  activate object worksheet "{sheet}" of active workbook\n'
        f'  select range "A{row}:AE{row}" of worksheet "{sheet}" of active workbook\n'
        f'  set scroll row of active window to {scroll_to}\n'
        f'end tell')
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True,
                           text=True, timeout=40)
    except subprocess.TimeoutExpired:
        return {"ok": False, "sheet": sheet, "row": row,
                "error": "Excel не ответил (если macOS спросил разрешение — нажмите OK и повторите)"}
    except Exception as e:  # noqa: BLE001
        subprocess.run(["open", str(MAIN_XLSX)])
        return {"ok": True, "sheet": sheet, "row": row,
                "note": f"открыл файл; к строке {row} перейдите вручную ({type(e).__name__})"}
    if r.returncode != 0:
        # типовой случай: нет права Automation (Терминал → Microsoft Excel)
        subprocess.run(["open", str(MAIN_XLSX)])
        hint = ("нет права управлять Excel: Системные настройки → Конфиденциальность "
                "и безопасность → Автоматизация → Терминал → включить Microsoft Excel")
        err = (r.stderr or "").strip().splitlines()
        return {"ok": True, "sheet": sheet, "row": row,
                "note": f"открыл файл, но без перехода к строке {row} — {hint}"
                        + (f" [{err[-1][:120]}]" if err else "")}
    return {"ok": True, "sheet": sheet, "row": row}


# ---- гео-анализ локации (OSM Overpass/Nominatim, бесплатно, без ключей) ----
OVERPASS_UA = "realty-tool/1.0 (commercial-realty enrichment)"  # браузерный UA Overpass режет (406)
# зеркала Overpass нестабильны ПООЧЕРЁДНО (проверено: то 504 у главного, то таймаут kumi) →
# попытки чередуют зеркала
OVERPASS_MIRRORS = ["https://overpass-api.de/api/interpreter",
                    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
                    "https://overpass.kumi.systems/api/interpreter"]
NOMINATIM = "https://nominatim.openstreetmap.org/search"
GEO_CACHE_FILE = WEB_DIR / "geo_cache.json"     # вечный кэш: окружение меняется медленно
_cache_lock = threading.Lock()


def _json_cache(path):
    with contextlib.suppress(Exception):
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


GEO_CACHE = _json_cache(GEO_CACHE_FILE)


def _cache_put(cache, path, key, val):
    with _cache_lock:
        cache[key] = val
        path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


# Nominatim спотыкается о префиксы «г./ул./просп.» и о хвост «, Беларусь» (проверено:
# с ними None, без них находит; страна — через параметр countrycodes=by, не текстом)
_ADDR_PREFIX = re.compile(r"\b(г|город|ул|улица|просп|проспект|пр-т|пер|переулок|б-р|бульвар"
                          r"|наб|набережная|ш|шоссе|д|дом|аг|р-н|район|обл|область)\.?(?=\s|,|$)", re.I)


def _geocode(addr):
    """Адрес → [lat, lng] через Nominatim (объекты без координат — в основном realt)."""
    q = re.sub(r"\s+", " ", _ADDR_PREFIX.sub("", addr)).replace(" ,", ",").strip(" ,")
    params = urllib.parse.urlencode({"q": q, "format": "json", "limit": "1", "countrycodes": "by"})
    req = urllib.request.Request(NOMINATIM + "?" + params, headers={"User-Agent": OVERPASS_UA})
    with contextlib.suppress(Exception):
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.loads(r.read().decode("utf-8", "replace"))
        if d:
            return [float(d[0]["lat"]), float(d[0]["lon"])]
    return None


def _haversine_m(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(a))


_FOOD = {"cafe", "restaurant", "fast_food", "bar"}
_POI_AMENITY = _FOOD | {"pharmacy", "bank", "marketplace"}


def api_geo(hsh):
    """Окружение объекта: POI в 300 м по категориям + ближайший транспорт в 800 м.
    Шкала активности та же, что в save_marked.py (сопоставимо с сохранёнками)."""
    if not hsh or hsh not in INDEX:
        return {"ok": False, "error": "объект не найден"}
    if hsh in GEO_CACHE:
        return GEO_CACHE[hsh]
    it = INDEX[hsh]
    coords, geocoded = it.get("coords"), False
    if not coords:
        if not it.get("addr"):
            return {"ok": False, "error": "у объекта нет ни координат, ни адреса"}
        coords, geocoded = _geocode(it["addr"]), True
        if not coords:
            return {"ok": False, "error": "адрес не геокодировался"}
    lat, lng = coords
    q = (f"[out:json][timeout:25];("
         f"node(around:800,{lat},{lng})[shop];"
         f"node(around:800,{lat},{lng})[amenity~'^(cafe|restaurant|fast_food|bar|pharmacy|bank|marketplace|school|kindergarten)$'];"
         f"node(around:800,{lat},{lng})[office];"
         f"node(around:800,{lat},{lng})[highway=bus_stop];"
         f"node(around:800,{lat},{lng})[railway~'^(station|tram_stop)$'];"
         f"node(around:800,{lat},{lng})[station=subway];"
         f");out body;")
    els = None
    for mirror in OVERPASS_MIRRORS:
        try:
            data = urllib.parse.urlencode({"data": q}).encode()
            req = urllib.request.Request(mirror, data=data, headers={"User-Agent": OVERPASS_UA})
            with urllib.request.urlopen(req, timeout=40) as r:
                els = json.loads(r.read().decode("utf-8", "replace")).get("elements", [])
            break
        except urllib.error.HTTPError as e:
            err = f"OSM недоступен (HTTP {e.code})"
        except Exception as e:
            err = f"OSM недоступен ({type(e).__name__})"
    if els is None:           # сбой сети НЕ кэшируем — следующий клик попробует снова
        return {"ok": False, "error": err}
    c = {"poi": 0, "shops": 0, "food": 0, "pharmacies": 0, "offices": 0, "schools": 0}
    transit = None
    for el in els:
        t, la, lo = el.get("tags", {}), el.get("lat"), el.get("lon")
        if la is None:
            continue
        d = _haversine_m(lat, lng, la, lo)
        if (t.get("highway") == "bus_stop" or t.get("railway") in ("station", "tram_stop")
                or t.get("station") == "subway"):
            transit = d if transit is None else min(transit, d)
            continue
        if d > 300:
            continue
        if t.get("amenity") in ("school", "kindergarten"):
            c["schools"] += 1
            continue                                  # школы — контекст, в «активность» не входят
        c["poi"] += 1
        if "shop" in t:
            c["shops"] += 1
        if t.get("amenity") in _FOOD:
            c["food"] += 1
        if t.get("amenity") == "pharmacy":
            c["pharmacies"] += 1
        if "office" in t:
            c["offices"] += 1
    act = ("высокая" if c["poi"] >= 40 else "средняя" if c["poi"] >= 12
           else "низкая" if c["poi"] else "очень низкая")
    res = {"ok": True, "activity": act, **c,
           "transit_m": int(transit) if transit is not None else None,
           "coords": [lat, lng], "geocoded": geocoded}
    _cache_put(GEO_CACHE, GEO_CACHE_FILE, hsh, res)
    return res


# ---- AI-вердикт по объекту: Groq gpt-oss-120b (мощнее) → fallback GLM/z.ai. Оба бесплатны ----
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
GROQ_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")  # Cloudflare банит python-UA (1010)
ZAI_URL = "https://api.z.ai/api/paas/v4/chat/completions"
ZAI_MODEL = "glm-4.5-flash"
VERDICT_CACHE_FILE = WEB_DIR / "verdict_cache.json"
VERDICT_CACHE = _json_cache(VERDICT_CACHE_FILE)
_VERDICT_SYS = ("Ты — аналитик коммерческой недвижимости Беларуси, помогаешь лидогенератору "
                "при обзвоне собственников. Отвечай по-русски, кратко и конкретно, "
                "без воды и без markdown-разметки.")


def _key_from(env, fname):
    k = os.environ.get(env) or ""
    f = Path.home() / fname
    if not k and f.exists():
        k = f.read_text(encoding="utf-8").strip()
    return k


def _ai_providers():
    """Каскад бесплатных нейронок по убыванию силы; без ключа провайдер пропускается."""
    out = []
    gk = _key_from("GROQ_API_KEY", ".groq_key")
    if gk:
        out.append(("Groq gpt-oss-120b", GROQ_URL,
                    {"Authorization": f"Bearer {gk}", "User-Agent": GROQ_UA},
                    {"model": GROQ_MODEL, "reasoning_effort": "low"}))
    zk = _key_from("ZAI_API_KEY", ".zai_key")
    if zk:
        out.append(("GLM-4.5-flash", ZAI_URL, {"Authorization": f"Bearer {zk}"},
                    {"model": ZAI_MODEL,
                     "thinking": {"type": "disabled"}}))  # иначе размышления съедают max_tokens
    return out


def api_verdict(hsh, stats):
    if not hsh or hsh not in INDEX:
        return {"ok": False, "error": "объект не найден"}
    it = INDEX[hsh]
    ck = f"{hsh}|{it.get('usd') or it.get('price') or ''}"  # смена цены → вердикт пересчитается
    if ck in VERDICT_CACHE:
        return VERDICT_CACHE[ck]
    providers = _ai_providers()
    if not providers:
        return {"ok": False, "error": "нет ключей нейронок (~/.groq_key / ~/.zai_key)"}
    geo = GEO_CACHE.get(hsh) or {}
    facts = {"тип": it.get("type"), "сделка": "аренда" if it.get("deal") == "rent" else "продажа",
             "город": it.get("city"), "адрес": it.get("addr"), "площадь_м2": it.get("area"),
             "цена": it.get("usd") or it.get("price"), "этаж": it.get("floor"),
             "рынок": stats or "нет данных",
             "локация_OSM": ({"активность_окружения": geo.get("activity"),
                              "точек_бизнеса_в_300м": geo.get("poi"),
                              "магазинов": geo.get("shops"), "общепита": geo.get("food"),
                              "аптек": geo.get("pharmacies"), "офисов": geo.get("offices"),
                              "школ_садов": geo.get("schools"),
                              "метров_до_остановки": geo.get("transit_m")}
                             if geo.get("ok") else "нет данных")}
    prompt = (f"Объект и данные (JSON):\n{json.dumps(facts, ensure_ascii=False)}\n\n"
              "Дай вердикт ровно тремя короткими абзацами:\n"
              "1. Цена против рынка (по данным «рынок»).\n"
              "2. Кому объект подойдёт (арендаторы/использование) с учётом «локация_OSM».\n"
              "3. Что упомянуть в разговоре с собственником при обзвоне.\n"
              "Не выдумывай факты, которых нет в данных; чисел не изобретай.\n"
              "Поля рынок.позиция_к_медиане и рынок.cap_rate_оценка — ГОТОВЫЕ выводы, бери их "
              "дословно; сам числа НЕ сравнивай и хорошесть доходности НЕ оценивай.")
    text, used, err = None, None, "нейронки недоступны"
    for name, url, hdrs, extra in providers:
        for _ in (1, 2):      # под VPN первое соединение бывает обрывается — один повтор
            body = json.dumps({**extra, "temperature": 0.3, "max_tokens": 800,
                               "messages": [{"role": "system", "content": _VERDICT_SYS},
                                            {"role": "user", "content": prompt}]}).encode()
            req = urllib.request.Request(url, data=body,
                                         headers={"Content-Type": "application/json", **hdrs})
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    d = json.loads(r.read().decode("utf-8", "replace"))
                text = (d["choices"][0]["message"]["content"] or "").strip()
            except Exception as e:  # сбой не кэшируем
                err = f"{name}: {type(e).__name__}"
                time.sleep(1)
                continue
            if text:
                used = name
                break
            err = f"{name}: пустой ответ"
        if text:
            break
    if not text:
        return {"ok": False, "error": err}
    res = {"ok": True, "text": text, "model": used}
    _cache_put(VERDICT_CACHE, VERDICT_CACHE_FILE, ck, res)
    return res


# ---- HTTP ----
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WEB_DIR), **k)

    def log_message(self, *a):
        pass

    def end_headers(self):
        # WKWebView (RealtyApp) жёстко кэширует css/js/html → правки не видны без переустановки.
        # Запрещаем кэш статики, чтобы изменения подхватывались сразу после reload.
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # чтобы страница, открытая как file://, могла найти сервер (ping) и перепрыгнуть
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_image(self, hsh):
        p = fetch_photo(hsh)
        if not p:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        data = p.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _IMG_CT.get(p.suffix, "image/jpeg"))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self):
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        with contextlib.suppress(Exception):
            return json.loads(self.rfile.read(n).decode("utf-8"))
        return {}

    def do_GET(self):
        route = self.path.split("?")[0].rstrip("/")
        if route == "/api/ping":
            return self._send_json({"ok": True, "app": "realty-dashboard"})
        if route == "/api/saved":
            return self._send_json({"hashes": list_saved()})
        if route == "/api/photo":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            return self._send_json(api_photo((q.get("hash") or [""])[0].strip()))
        if route == "/img":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            return self._send_image((q.get("hash") or [""])[0].strip())
        if route == "/api/geo":
            from urllib.parse import parse_qs, urlparse
            q = parse_qs(urlparse(self.path).query)
            return self._send_json(api_geo((q.get("hash") or [""])[0].strip()))
        if route == "/api/update/status":
            return self._send_json({k: JOB[k] for k in JOB})
        return super().do_GET()

    def do_POST(self):
        route = self.path.split("?")[0].rstrip("/")
        if route == "/api/reveal":
            return self._send_json(reveal((self._read_json().get("hash") or "").strip()))
        if route == "/api/save":
            return self._send_json(save_ad((self._read_json().get("hash") or "").strip()))
        if route == "/api/verdict":
            b = self._read_json()
            return self._send_json(api_verdict((b.get("hash") or "").strip(), b.get("stats")))
        if route == "/api/update":
            if JOB["running"]:
                return self._send_json({"ok": False, "error": "уже выполняется"})
            target = (self._read_json().get("target") or "all").strip()
            if target not in ("all", "realty", "geo", "auctions", "banks"):
                target = "all"
            threading.Thread(target=_run_update, args=(target,), daemon=True).start()
            time.sleep(0.2)
            return self._send_json({"ok": True})
        if route == "/api/update/stop":
            if _proc:
                _proc.terminate()
            return self._send_json({"ok": True})
        return self._send_json({"ok": False, "error": "неизвестный метод"}, 404)


def free_port(start):
    for p in range(start, start + 50):
        with contextlib.closing(socket.socket()) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def main():
    sys.path.insert(0, str(WEB_DIR))  # чтобы import fetch_ad работал из любого cwd
    load_index()
    load_photo_cache()
    if not INDEX:
        print("⚠️  Нет данных — сначала: ./bin/python web/export_data.py")
    port = free_port(START_PORT)
    url = f"http://localhost:{port}/index.html"
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"\n  Консоль обзвона запущена:  {url}", flush=True)
        print(f"  Объектов в индексе: {len(INDEX)}", flush=True)
        print("  Это окно держит сервер. Не закрывайте, пока пользуетесь дашбордом.", flush=True)
        print("  Остановить: Ctrl+C или закрыть окно.\n", flush=True)
        import os
        import webbrowser
        if not os.environ.get("REALTY_NO_BROWSER"):  # в Mac-приложении дашборд в WKWebView — Safari не нужен
            webbrowser.open(url)
        with contextlib.suppress(KeyboardInterrupt):
            httpd.serve_forever()
        print("\n  Сервер остановлен.")


if __name__ == "__main__":
    main()

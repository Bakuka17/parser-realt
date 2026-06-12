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
import re
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

import fetch_ad  # web/ в sys.path, см. main()

WEB_DIR = Path(__file__).resolve().parent
ROOT = WEB_DIR.parent
DATA_JS = WEB_DIR / "data.js"
SAVED_DIR = WEB_DIR / "saved"
MAIN_XLSX = ROOT / "commercial_realty.xlsx"
START_PORT = 8765
SHEETS = {"Продажа", "Аренда"}  # белый список для AppleScript

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


def _run_update():
    global _proc
    py = sys.executable
    warn = ""
    if (ROOT / "~$commercial_realty.xlsx").exists():
        warn = ("⚠ commercial_realty.xlsx сейчас ОТКРЫТ в Excel — запись может не пройти.\n"
                "  Закройте файл в Excel и запустите обновление снова.\n\n")
    JOB.update(running=True, started=datetime.now().strftime("%H:%M:%S"),
               finished="", rc=None,
               log=warn + "Запуск collect_realty.py (инкрементально)…\n")
    try:
        _proc = subprocess.Popen([py, "-u", "collect_realty.py"], cwd=str(ROOT),
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, bufsize=1)
        for line in _proc.stdout:
            JOB["log"] = (JOB["log"] + line)[-8000:]
        _proc.wait()
        rc = _proc.returncode
        JOB["log"] += f"\ncollect завершён (код {rc}). Ре-экспорт данных…\n"
        ex = subprocess.run([py, "web/export_data.py"], cwd=str(ROOT),
                            capture_output=True, text=True)
        JOB["log"] = (JOB["log"] + ex.stdout + ex.stderr)[-8000:]
        load_index()
        JOB.update(rc=rc)
        JOB["log"] += "\nГотово. Обновите страницу.\n"
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
    """Телефоны прямо в тексте объявления (kufar так делает в ~7% случаев)."""
    out = []
    for m in PHONE_RE.findall(text or ""):
        n = re.sub(r"[\s\-()]", "", m)
        if n.startswith("80"):
            n = "+375" + n[2:]
        elif not n.startswith("+"):
            n = "+" + n
        if n not in out:
            out.append(n)
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


# ---- HTTP ----
class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WEB_DIR), **k)

    def log_message(self, *a):
        pass

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # чтобы страница, открытая как file://, могла найти сервер (ping) и перепрыгнуть
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

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
        if route == "/api/update/status":
            return self._send_json({k: JOB[k] for k in JOB})
        return super().do_GET()

    def do_POST(self):
        route = self.path.split("?")[0].rstrip("/")
        if route == "/api/reveal":
            return self._send_json(reveal((self._read_json().get("hash") or "").strip()))
        if route == "/api/save":
            return self._send_json(save_ad((self._read_json().get("hash") or "").strip()))
        if route == "/api/update":
            if JOB["running"]:
                return self._send_json({"ok": False, "error": "уже выполняется"})
            threading.Thread(target=_run_update, daemon=True).start()
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
        import webbrowser
        webbrowser.open(url)
        with contextlib.suppress(KeyboardInterrupt):
            httpd.serve_forever()
        print("\n  Сервер остановлен.")


if __name__ == "__main__":
    main()

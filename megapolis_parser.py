"""megapolis_parser — скрейпер megapolis-real.by → Excel (схема как у realt.by).

Megapolis отдаёт серверный HTML со всеми полями (включая телефоны и дату)
прямо в списке, поэтому детальные страницы не нужны. Переиспользует машинерию
realty_parser_v8 (write_excel, load_prev_db, инкрементал, чекпойнты, классификатор «Здание»).

Запуск:
  ./bin/python megapolis_parser.py                 # инкрементальный
  ./bin/python megapolis_parser.py --max-pages 3   # ограничить глубину
  ./bin/python megapolis_parser.py --full           # полный перепрогон
"""
from __future__ import annotations

import argparse
import html as _html
import random
import re
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Optional

import realty_parser_v8 as R

HERE = Path(__file__).parent
DEFAULT_OUT = HERE / "megapolis_realty.xlsx"
BASE = "https://megapolis-real.by"
SOURCE = "megapolis-real.by"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
CHECKPOINT_EVERY = 200  # объявлений между сохранениями

# (путь категории, тип сделки, тип объекта)
CATEGORIES = [
    ("ofisnaya_nedvizhimost/arenda", "Аренда", "Офис"),
    ("ofisnaya_nedvizhimost/prodazha-pokupka", "Продажа", "Офис"),
    ("torgovaya-nedvizhimost/arenda", "Аренда", "Торговое"),
    ("torgovaya-nedvizhimost/prodazha-pokupka", "Продажа", "Торговое"),
    ("skladskaya-nedvizhimost/arenda", "Аренда", "Склад"),
    ("skladskaya-nedvizhimost/prodazha-pokupka", "Продажа", "Склад"),
]


def fetch(url: str, retries: int = 3) -> str:
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
            return raw.decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * attempt)
    print(f"    ✖ fetch {url}: {last}")
    return ""


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _grab(section: str, cls: str) -> str:
    m = re.search(r'class="' + cls + r'"[^>]*>(.*?)</', section, re.S)
    return _clean(m.group(1)) if m else ""


def split_sections(page_html: str) -> list[str]:
    """Режет страницу на секции отдельных объявлений (<section class="rItem ...">)."""
    out = []
    for m in re.finditer(r'<section class="rItem[^"]*">', page_html):
        start = m.start()
        end = page_html.find("</section>", start)
        if end == -1:
            continue
        sec = page_html[start:end]
        if "data-go-url" in sec and "rInfo_zagol" in sec:
            out.append(sec)
    return out


def parse_price(section: str) -> tuple[str, str]:
    """Возвращает (Цена общая, Цена за м²)."""
    byn = re.search(r'class="rInfo_pricetotal price_byn"[^>]*>(.*?)</', section, re.S)
    usd = re.search(r'class="rInfo_pricetotal price_usd"[^>]*>(.*?)</', section, re.S)
    parts = []
    if byn:
        v = _clean(byn.group(1))
        if any(c.isdigit() for c in v):
            parts.append(v.replace("BYN", "р.").strip())
    if usd:
        v = _clean(usd.group(1)).replace("$", "").strip()
        if any(c.isdigit() for c in v):
            parts.append(v + " $")
    return " / ".join(parts), ""


def parse_owner(section: str) -> tuple[str, str]:
    """Возвращает (Контакт, Имя контакта)."""
    raw = _grab(section, "rInfo_owner")
    if not raw:
        return "", ""
    low = raw.lower()
    if "агент" in low:
        contact = "Агентство"
    elif "собственник" in low or "юр. лицо" in low or "частное" in low:
        contact = "Собственник / Частное лицо"
    else:
        contact = raw[:30]
    name_m = re.search(r"[:\-–]\s*(.+)$", raw)
    name = name_m.group(1).strip() if name_m else ""
    return contact, name


def parse_section(section: str, deal: str, type_: str) -> Optional[dict]:
    m = re.search(r'data-go-url="([^"]+)"', section)
    if not m:
        return None
    url = BASE + m.group(1) if m.group(1).startswith("/") else m.group(1)

    title = _grab(section, "rInfo_zagol")
    address = _grab(section, "rInfo_address tab_hidden") or _grab(section, "rInfo_address")
    punkt = _grab(section, "rInfo_punkt")
    # город из rInfo_punkt: «Минск , Фабрициуса, 8Б»
    city = ""
    if punkt:
        city_part = punkt.split(",")[0].strip()
        if city_part:
            city = "г. " + city_part
    area_raw = _grab(section, "rInfo_square")
    area = area_raw.replace(",", ".").strip() if area_raw else ""
    price_total, price_per = parse_price(section)
    pub_date = _grab(section, "rInfo_date")
    short = _grab(section, "rInfo_short")
    contact, name = parse_owner(section)
    phones = re.findall(r"tel:([+\d]+)", section)
    phone = ", ".join(dict.fromkeys(phones[:3]))

    # координаты: data-coord="lat,lng"
    coord_m = re.search(r'data-coord="([\d.]+),([\d.]+)"', section)
    coords = f"{coord_m.group(1)},{coord_m.group(2)}" if coord_m else ""
    # фото: megapolis lazy-load — реальный путь в data-src, src — заглушка blank_*.
    # пути обычно относительные (assets/cache/...), добавляем домен.
    imgs = re.findall(r'data-src="([^"]+?\.(?:jpg|jpeg|png|webp)[^"]*)"', section)
    imgs = [u for u in imgs if "blank_" not in u and "site/imgs" not in u and "logo" not in u.lower()]
    imgs = [u if u.startswith("http") else f"https://megapolis-real.by/{u.lstrip('/')}" for u in imgs]
    # без лимита: сохраняем все фото объявления, чтобы при «Сохранить» получить планировку и пр.
    photo_urls = ";".join(list(dict.fromkeys(imgs)))

    feats = R.parse_features(title + " " + short, short)
    blob = title + " " + short
    final_type = "Здание" if R.is_building_text(blob) else type_
    if final_type != "Здание" and type_ == "Склад" and re.search(r"производ", blob, re.I):
        final_type = "Производство"

    h = R.hashlib.md5(
        (R.normalize_url(url) + address + area + price_total).encode()
    ).hexdigest()[:12]

    item = {c: "н/у" for c in R.COLUMNS}
    item.update({
        "Тип": final_type,
        "Адрес": address or title[:60],
        "Район / Город": city,
        "Площадь, м²": area,
        "Цена общая": price_total,
        "Цена за м²": price_per,
        "Описание": R.clean_description(short),
        "Этаж / этажность": "",
        "Год постройки": "н/у",
        "Класс здания": feats["building_class"],
        "Состояние": "н/у",
        "НДС": feats["nds"],
        "Парковка": feats["parking"],
        "Отдельный вход": feats["separate_entrance"],
        "Мокрая зона": feats["wet_zone"],
        "Контакт": contact,
        "Имя контакта": name,
        "Телефон": phone,
        "Ссылка": url,
        "Дата публикации": pub_date,
        "Источник": SOURCE,
        "Высота потолков, м": feats["ceiling_height"],
        "Грузовая рампа / ворота": feats["ramp_gate"],
        "Электр. мощность, кВт": "н/у",
        "Витринные окна / 1-я линия": feats["showcase"],
        "Мин. срок аренды": feats["min_rent"],
        "Материал стен": "н/у",
        "Сохранить": "",
        "Фото URL": photo_urls,
        "Координаты": coords,
        "Хэш": h,
        "_deal": deal,
    })
    return item


def scrape_category(path: str, deal: str, type_: str, prev_urls: set,
                    last_run: Optional[date], cfg) -> list[dict]:
    print(f"\n→ {deal} / {type_}: /{path}/")
    results = []
    for page_n in range(1, cfg.max_pages + 1):
        url = f"{BASE}/realt/{path}/" + (f"?page={page_n}" if page_n > 1 else "")
        page_html = fetch(url)
        if not page_html:
            break
        sections = split_sections(page_html)
        if not sections:
            print(f"  стр.{page_n}: 0 объявлений → стоп")
            break
        items = [parse_section(s, deal, type_) for s in sections]
        items = [it for it in items if it]
        new_items = [it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls]
        all_known = bool(prev_urls) and not new_items and not cfg.full
        date_stop = False
        if last_run and not cfg.full:
            dates = [R.parse_pub_date(it.get("Дата публикации", "")) for it in items]
            valid = [d for d in dates if d]
            if valid and all(d < last_run for d in valid):
                date_stop = True
        print(f"  стр.{page_n}: всего {len(items)} | новых {len(new_items)} | известных {len(items)-len(new_items)}"
              + (" | DATE_STOP" if date_stop else "") + (" | ALL_KNOWN" if all_known else ""))
        results.extend(items)
        if all_known or date_stop:
            break
        time.sleep(random.uniform(3.0, 6.0))  # щадящая пауза против бана IP
    print(f"  ✓ из категории: {len(results)}")
    return results


def main() -> None:
    p = argparse.ArgumentParser(description="Скрейпер megapolis-real.by → Excel.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--max-pages", type=int, default=100)
    p.add_argument("--full", action="store_true", help="полный перепрогон, игнорировать БД")
    cfg = p.parse_args()
    cfg.out = cfg.out.expanduser().resolve()

    prev_db, last_run = R.load_prev_db(cfg.out)
    prev_urls = set() if cfg.full else set(prev_db.keys())
    snapshot: dict = {}
    for _u, _r in prev_db.items():
        d, hsh = _r.get("_deal"), _r.get("Хэш")
        if d and hsh:
            snapshot.setdefault(d, set()).add(str(hsh))

    mode = "ПОЛНЫЙ" if cfg.full else (
        f"инкрементальный (БД {len(prev_db)}"
        + (f", last_run={last_run:%d.%m.%Y}" if last_run else "") + ")"
        if prev_db else "первый прогон")
    print(f"🚀 megapolis_parser. Дата: {date.today():%d.%m.%Y}")
    print(f"   режим: {mode} | out={cfg.out}")

    all_new: list[dict] = []
    for ci, (path, deal, type_) in enumerate(CATEGORIES):
        if ci:
            time.sleep(random.uniform(4.0, 8.0))  # пауза между категориями
        items = scrape_category(path, deal, type_, prev_urls, last_run, cfg)
        new = [it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls]
        all_new.extend(new)
        # чекпойнт
        if len(all_new) >= CHECKPOINT_EVERY:
            base = [] if cfg.full else list(prev_db.values())
            R.write_excel(base + all_new, cfg.out, prev_hashes=snapshot)
            print(f"    💾 чекпойнт: {len(all_new)} новых")

    base = [] if cfg.full else list(prev_db.values())
    final = base + all_new
    print(f"\n📦 Итог: {len(final)} (новых: {len(all_new)}, из БД: {len(final)-len(all_new)})")
    R.write_excel(final, cfg.out, prev_hashes=snapshot)


if __name__ == "__main__":
    main()

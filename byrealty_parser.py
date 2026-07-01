"""byrealty_parser — скрейпер byrealty.by (коммерция) → Excel (схема как у realt.by).

byrealty (движок Sitebill) отдаёт серверный HTML со всеми полями ПРЯМО В ЛИСТИНГЕ,
включая телефон и координаты — детальные страницы не нужны (как megapolis).
Сайт небольшой: коммерции немного (десятки объявлений), пагинации нет.
Переиспользует машинерию realty_parser_v8 (write_excel, load_prev_db, инкрементал,
чекпойнты, классификатор «Здание», parse_features).

Запуск:
  ./bin/python byrealty_parser.py            # инкрементальный
  ./bin/python byrealty_parser.py --full     # полный перепрогон
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
DEFAULT_OUT = HERE / "byrealty_realty.xlsx"
BASE = "https://byrealty.by"
SOURCE = "byrealty.by"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
CHECKPOINT_EVERY = 50

# (путь категории, тип сделки)
CATEGORIES = [
    ("kommercheskaja-nedvizhimost/arenda", "Аренда"),
    ("kommercheskaja-nedvizhimost/prodaja", "Продажа"),
]

# подкатегория в URL объявления → тип объекта
SUBTYPE = {
    "ofisy": "Офис", "torgovye": "Торговое", "torgovye-pomescheniya": "Торговое",
    "sklady": "Склад", "skladskie": "Склад", "proizvodstvo": "Производство",
    "proizvodstvennye": "Производство", "obshchepit": "Общепит",
    "zdaniya": "Здание", "uchastki": "Участок", "garaji": "Гараж",
}


def fetch(url: str, retries: int = 3) -> str:
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * attempt)
    print(f"    ✖ fetch {url}: {last}")
    return ""


def _clean(s: str) -> str:
    s = re.sub(r"<sup>.*?</sup>", "", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


def _grab(card: str, cls: str) -> str:
    m = re.search(r'class="' + re.escape(cls) + r'"[^>]*>(.*?)</', card, re.S)
    return _clean(m.group(1)) if m else ""


def split_cards(page_html: str) -> list[str]:
    """Каждая карточка начинается с <el data-id="..."> (скрытый адрес). Режем по ним."""
    idx = [m.start() for m in re.finditer(r'<el data-id="\d+"', page_html)]
    out = []
    for i, start in enumerate(idx):
        end = idx[i + 1] if i + 1 < len(idx) else page_html.find("</footer>", start)
        out.append(page_html[start:end if end > 0 else start + 4000])
    return out


def parse_price(card: str, deal: str) -> tuple[str, str]:
    """(Цена общая, Цена за м²) из блока item_prices. Аренда → итог за месяц."""
    block_m = re.search(r'class="item_prices".*?(?=class="item_more_info"|</section|$)', card, re.S)
    block = block_m.group(0) if block_m else card
    amounts = re.findall(r'class="currency-amount">(.*?)</el>', block, re.S)
    signs = re.findall(r'class="currency-sign">(.*?)</el>', block, re.S)
    if not amounts:
        return "", ""
    total = _clean(amounts[0]) + (" " + _clean(signs[0]) if signs else "")
    per = ""
    if len(amounts) > 1:
        per = _clean(amounts[1]) + (" " + _clean(signs[1]) if len(signs) > 1 else "")
    return total.strip(), per.strip()


def parse_card(card: str, deal: str) -> Optional[dict]:
    m = re.search(r'href="(/kommercheskaja-nedvizhimost/[^"]*?/realty-(\d+))"', card)
    if not m:
        return None
    url = BASE + m.group(1)
    subcat = m.group(1).split("/")[3] if len(m.group(1).split("/")) > 3 else ""
    type_ = SUBTYPE.get(subcat, "Помещение")

    title = _grab(card, "main-link")
    # адрес из скрытого <el data-id> (полнее) либо из item_adress
    addr_m = re.search(r'<el data-id="\d+"[^>]*>(.*?)</el>', card, re.S)
    address = _clean(addr_m.group(1)) if addr_m else _grab(card, "main-link")
    city = ""
    if address:
        first = address.split(",")[0].strip()
        if first:
            city = "г. " + first
    metro = _grab(card, "state-block")  # «м. Грушевка»
    desc = _grab(card, "text-property-info")
    price_total, price_per = parse_price(card, deal)

    # площадь из item_more_info («250 м²»)
    more = re.search(r'class="item_more_info">(.*?)</div>\s*</div>', card, re.S)
    more_txt = _clean(more.group(1)) if more else ""
    area_m = re.search(r"(\d+(?:[.,]\d+)?)\s*м", more_txt)
    area = area_m.group(1).replace(",", ".") if area_m else ""

    # телефон прямо в листинге (phones_popup_link)
    phones = re.findall(r"\+375[\s()\-]*\d{2}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}", card)
    phone = ", ".join(dict.fromkeys(re.sub(r"[\s()\-]", "", p) for p in phones[:3]))

    # координаты data-lat/data-lng
    lat = re.search(r'data-lat="([\d.]+)"', card)
    lng = re.search(r'data-lng="([\d.]+)"', card)
    coords = f"{lat.group(1)},{lng.group(1)}" if lat and lng else ""

    # фото /img/data/...
    imgs = re.findall(r'src="(/img/data/[^"]+\.(?:jpg|jpeg|png|webp))"', card)
    imgs = [u if u.startswith("http") else BASE + u for u in imgs]
    photo_urls = ";".join(dict.fromkeys(imgs))

    blob = title + " " + desc
    final_type = "Здание" if R.is_building_text(blob) else type_
    feats = R.parse_features(blob, desc)
    if metro:
        desc = (desc + f" [{metro}]").strip()

    h = R.hashlib.md5((R.normalize_url(url) + address + area + price_total).encode()).hexdigest()[:12]

    item = {c: "н/у" for c in R.COLUMNS}
    item.update({
        "Тип": final_type,
        "Адрес": address or title[:60],
        "Район / Город": city,
        "Площадь, м²": area,
        "Цена общая": price_total,
        "Цена за м²": price_per,
        "Описание": R.clean_description(desc),
        "Класс здания": feats["building_class"],
        "НДС": feats["nds"],
        "Парковка": feats["parking"],
        "Отдельный вход": feats["separate_entrance"],
        "Мокрая зона": feats["wet_zone"],
        "Высота потолков, м": feats["ceiling_height"],
        "Грузовая рампа / ворота": feats["ramp_gate"],
        "Витринные окна / 1-я линия": feats["showcase"],
        "Мин. срок аренды": feats["min_rent"],
        "Контакт": "", "Имя контакта": "",
        "Телефон": phone,
        "Ссылка": url,
        "Дата публикации": "",
        "Источник": SOURCE,
        "Сохранить": "",
        "Фото URL": photo_urls,
        "Координаты": coords,
        "Хэш": h,
        "_deal": deal,
    })
    return item


def scrape_category(path: str, deal: str, prev_urls: set, last_run, cfg) -> list[dict]:
    print(f"\n→ {deal}: /{path}")
    page_html = fetch(f"{BASE}/{path}")
    if not page_html:
        return []
    cards = split_cards(page_html)
    items = [parse_card(c, deal) for c in cards]
    items = [it for it in items if it]
    new = [it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls]
    print(f"  всего {len(items)} | новых {len(new)}")
    return items


def main() -> None:
    p = argparse.ArgumentParser(description="Скрейпер byrealty.by (коммерция) → Excel.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--max-pages", type=int, default=1)  # byrealty без пагинации
    p.add_argument("--full", action="store_true")
    cfg = p.parse_args()
    cfg.out = cfg.out.expanduser().resolve()

    prev_db, last_run = R.load_prev_db(cfg.out)
    prev_urls = set() if cfg.full else set(prev_db.keys())
    snapshot: dict = {}
    for _u, _r in prev_db.items():
        d, hsh = _r.get("_deal"), _r.get("Хэш")
        if d and hsh:
            snapshot.setdefault(d, set()).add(str(hsh))

    print(f"🚀 byrealty_parser. Дата: {date.today():%d.%m.%Y}")
    print(f"   режим: {'ПОЛНЫЙ' if cfg.full else 'инкрементальный'} | БД {len(prev_db)} | out={cfg.out}")

    all_new: list[dict] = []
    for ci, (path, deal) in enumerate(CATEGORIES):
        if ci:
            time.sleep(random.uniform(2.0, 4.0))
        items = scrape_category(path, deal, prev_urls, last_run, cfg)
        all_new.extend(it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls)

    base = [] if cfg.full else list(prev_db.values())
    final = base + all_new
    print(f"\n📦 Итог: {len(final)} (новых: {len(all_new)}, из БД: {len(final)-len(all_new)})")
    R.write_excel(final, cfg.out, prev_hashes=snapshot)


if __name__ == "__main__":
    main()

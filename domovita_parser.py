"""domovita_parser — скрейпер domovita.by (коммерция) → Excel (схема как у realt.by).

⚠ ГЕО-БЛОК: domovita под иностранным IP отдаёт nginx 423. ЗАПУСКАТЬ С БЕЛОРУССКОГО IP
(VPN/Psiphon ВЫКЛЮЧЕН) — как kufar_phones.py. Под VPN парсер просто получит 423 и ничего
не соберёт.

Структура: серверный HTML. Листинг (тип/адрес/площадь/цена/фото) — сразу;
телефон (data-phone) и координаты — на деталке. Категории коммерции:
office/warehouses/shopping/service × sale/rent. Города пока Минск (основной рынок;
для регионов добавить города в CITIES). Переиспользует realty_parser_v8.

Запуск (БЕЗ VPN!):
  ./bin/python domovita_parser.py                # инкрементальный (телефоны с деталок)
  ./bin/python domovita_parser.py --max-pages 2  # тест
  ./bin/python domovita_parser.py --no-details   # быстрый листинг без телефонов
  ./bin/python domovita_parser.py --full
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
DEFAULT_OUT = HERE / "domovita_realty.xlsx"
BASE = "https://domovita.by"
SOURCE = "domovita.by"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
CHECKPOINT_EVERY = 100
CITIES = ["minsk"]  # ponytail: основной рынок; регионы — добавить города сюда
CITY_RU = {"minsk": "Минск", "brest": "Брест", "gomel": "Гомель", "grodno": "Гродно",
           "vitebsk": "Витебск", "mogilev": "Могилёв"}
# (категория, тип сделки, тип объекта)
CATS = [("office", "Офис"), ("warehouses", "Склад"),
        ("shopping", "Торговое"), ("service", "Услуги")]
DEAL_PATHS = [("sale", "Продажа"), ("rent", "Аренда")]


def fetch(url: str, retries: int = 3) -> str:
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:  # noqa: BLE001
            if e.code == 423:
                print("    ✖ 423 Locked — нужен БЕЛОРУССКИЙ IP (выключи VPN/Psiphon)")
                return ""
            last = e
            time.sleep(1.5 * attempt)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * attempt)
    print(f"    ✖ fetch {url}: {last}")
    return ""


def _clean(s: str) -> str:
    s = re.sub(r"<sup>.*?</sup>", "", s, flags=re.S)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


def split_cards(page_html: str) -> list[str]:
    """Карточка = от одного found_img до следующего."""
    idx = [m.start() for m in re.finditer(r'class="found_img', page_html)]
    out = []
    for i, start in enumerate(idx):
        end = idx[i + 1] if i + 1 < len(idx) else start + 9000
        out.append(page_html[start:end])
    return out


def parse_price(card: str) -> tuple[str, str]:
    """(Цена общая, Цена за м²). У domovita цена-калькулятор: за-м² в price-container,
    общая BYN в 'gr fs-14> NNN р.', USD в price-usd-group."""
    s = _html.unescape(card).replace("\xa0", " ").replace(" ", " ")
    per = ""
    pc = re.search(r'class="price-container[^"]*"[^>]*>\s*([\d ]+)\s*р\.\s*за\s*м', s)
    if pc:
        per = re.sub(r"\s+", " ", pc.group(1)).strip() + " р./м²"
    total = []
    tb = re.search(r'class="gr fs-14">\s*([\d ]{4,})\s*р\.\s*<', s)
    if tb:
        total.append(re.sub(r"\s+", " ", tb.group(1)).strip() + " р.")
    tu = re.search(r'class="price-usd[^"]*"[^>]*>\s*≈?\s*([\d ]+)\s*\$', s)
    if tu:
        total.append(re.sub(r"\s+", " ", tu.group(1)).strip() + " $")
    return " / ".join(total), per


def parse_card(card: str, deal: str, type_: str, city: str) -> Optional[dict]:
    m = re.search(r'class="link-object"\s+href="(' + re.escape(BASE) + r'/[^"]+)"', card)
    if not m:
        return None
    url = m.group(1)

    title = _clean((re.search(r'class="[^"]*title--listing[^"]*"[^>]*>(.*?)</a>', card, re.S)
                    or [None, ""])[1])
    # район/метро из первого .gr после map-marker
    reg = re.search(r'fa-map-marker[^<]*</i>\s*([^<]+)', card)
    region = _clean(reg.group(1)) if reg else ""
    metro = ""
    mt = re.search(r'class="udg_mark[^"]*">.*?</div>\s*<div class="gr">([^<]+)</div>', card, re.S)
    if mt:
        metro = _clean(mt.group(1))
    area = ""
    am = re.search(r">\s*([\d.,]+)\s*м<sup>2", card) or re.search(r">\s*([\d.,]+)\s*м²", card)
    if am:
        area = am.group(1).replace(",", ".")
    price_total, price_per = parse_price(card)

    imgs = re.findall(r'data-url-img="([^"]+)"', card)
    photo_urls = ";".join(dict.fromkeys(u.replace(".mobi.", ".") for u in imgs))

    desc_m = re.search(r'class="text-block">(.*?)</div>', card, re.S)
    desc = _clean(desc_m.group(1)) if desc_m else ""
    if metro:
        desc = (desc + f" [м. {metro}]").strip()

    blob = title + " " + desc
    final_type = "Здание" if R.is_building_text(blob) else type_
    feats = R.parse_features(blob, desc)
    h = R.hashlib.md5((R.normalize_url(url) + title + area + price_total).encode()).hexdigest()[:12]

    item = {c: "н/у" for c in R.COLUMNS}
    item.update({
        "Тип": final_type,
        "Адрес": title or url,
        "Район / Город": f"г. {CITY_RU.get(city, city.capitalize())}" + (f", {region.rstrip('; ')}" if region else ""),
        "Площадь, м²": area,
        "Цена общая": price_total,
        "Цена за м²": price_per,
        "Описание": R.clean_description(desc),
        "Класс здания": feats["building_class"], "НДС": feats["nds"],
        "Парковка": feats["parking"], "Отдельный вход": feats["separate_entrance"],
        "Мокрая зона": feats["wet_zone"], "Высота потолков, м": feats["ceiling_height"],
        "Грузовая рампа / ворота": feats["ramp_gate"], "Витринные окна / 1-я линия": feats["showcase"],
        "Мин. срок аренды": feats["min_rent"],
        "Контакт": "", "Имя контакта": "",
        "Телефон": "",
        "Ссылка": url, "Дата публикации": "", "Источник": SOURCE,
        "Сохранить": "", "Фото URL": photo_urls, "Координаты": "",
        "Хэш": h, "_deal": deal,
    })
    return item


def parse_detail(html_text: str) -> tuple[str, str]:
    """Деталь → (телефон, координаты). Телефон в data-phone, коорд в data-lat/lng или ld+json."""
    phones = re.findall(r'data-phone="(\+?375\d{9})"', html_text)
    if not phones:
        phones = re.findall(r"\+375\d{9}", html_text)
    phone = ", ".join("+" + p.lstrip("+") for p in dict.fromkeys(phones[:3]))
    coords = ""
    c = (re.search(r'data-lat="([\d.]+)"[^>]*data-l[no]ng?="([\d.]+)"', html_text)
         or re.search(r'"lat(?:itude)?":\s*"?([\d.]+)"?.*?"l[no]ng(?:itude)?":\s*"?([\d.]+)"?', html_text, re.S))
    if c:
        coords = f"{c.group(1)},{c.group(2)}"
    return phone, coords


def scrape_category(city: str, cat: str, type_: str, deal_path: str, deal: str,
                    prev_urls: set, cfg) -> list[dict]:
    print(f"\n→ {deal} / {type_}: /{city}/{cat}/{deal_path}")
    results: list[dict] = []
    for page_n in range(1, cfg.max_pages + 1):
        url = f"{BASE}/{city}/{cat}/{deal_path}" + (f"?page={page_n}" if page_n > 1 else "")
        page_html = fetch(url)
        if not page_html:
            break
        items = [parse_card(c, deal, type_, city) for c in split_cards(page_html)]
        items = [it for it in items if it]
        if not items:
            print(f"  стр.{page_n}: 0 → стоп")
            break
        new_items = [it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls]
        all_known = bool(prev_urls) and not new_items and not cfg.full
        print(f"  стр.{page_n}: всего {len(items)} | новых {len(new_items)}"
              + (" | ALL_KNOWN" if all_known else ""))
        results.extend(items)
        if all_known:
            break
        time.sleep(random.uniform(2.0, 4.0))

    if not cfg.no_details:
        todo = [it for it in results if R.normalize_url(it["Ссылка"]) not in prev_urls]
        print(f"  → телефоны/коорд {len(todo)} новых…")
        for i, it in enumerate(todo, 1):
            d = fetch(it["Ссылка"])
            if d:
                it["Телефон"], it["Координаты"] = parse_detail(d)
            time.sleep(random.uniform(1.5, 3.0))
    return results


def main() -> None:
    p = argparse.ArgumentParser(description="Скрейпер domovita.by (коммерция) → Excel. БЕЗ VPN!")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--max-pages", type=int, default=100)
    p.add_argument("--full", action="store_true")
    p.add_argument("--no-details", action="store_true", help="без телефонов/координат")
    cfg = p.parse_args()
    cfg.out = cfg.out.expanduser().resolve()

    prev_db, last_run = R.load_prev_db(cfg.out)
    prev_urls = set() if cfg.full else set(prev_db.keys())
    snapshot: dict = {}
    for _u, _r in prev_db.items():
        d, hsh = _r.get("_deal"), _r.get("Хэш")
        if d and hsh:
            snapshot.setdefault(d, set()).add(str(hsh))

    print(f"🚀 domovita_parser (БЕЗ VPN!). Дата: {date.today():%d.%m.%Y}")
    print(f"   режим: {'ПОЛНЫЙ' if cfg.full else 'инкрементальный'} | БД {len(prev_db)} | out={cfg.out}")

    all_new: list[dict] = []
    for city in CITIES:
        for cat, type_ in CATS:
            for deal_path, deal in DEAL_PATHS:
                items = scrape_category(city, cat, type_, deal_path, deal, prev_urls, cfg)
                all_new.extend(it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls)
                if len(all_new) >= CHECKPOINT_EVERY:
                    base = [] if cfg.full else list(prev_db.values())
                    R.write_excel(base + all_new, cfg.out, prev_hashes=snapshot)
                    print(f"    💾 чекпойнт: {len(all_new)} новых")
                time.sleep(random.uniform(2.0, 5.0))

    base = [] if cfg.full else list(prev_db.values())
    final = base + all_new
    print(f"\n📦 Итог: {len(final)} (новых: {len(all_new)}, из БД: {len(final)-len(all_new)})")
    R.write_excel(final, cfg.out, prev_hashes=snapshot)


if __name__ == "__main__":
    main()

"""edc_parser — скрейпер edc.sale (коммерция РБ) → Excel (схема как у realt.by).

⚠ ГЕО-БЛОК: edc.sale (российский хостинг) дропает TCP с иностранного IP (timeout).
ЗАПУСКАТЬ С БЕЛОРУССКОГО IP (VPN/Psiphon ВЫКЛЮЧЕН), как kufar_phones.py/domovita_parser.py.

Структура: серверный HTML, агрегатор по всей РБ. Листинг даёт тип/адрес-город/цену
(мультивалюта RUB/BYN/USD)/категорию/ссылку/фото. ⚠ ТЕЛЕФОН за JS (класс j-c-phones,
подгрузка по клику — как kufar) → в листинге/деталке простым GET его НЕТ. Телефон —
открытый TODO (реверс JS-эндпоинта, как был у kufar). Пока собираем без телефона.

Запуск (БЕЗ VPN!):
  ./bin/python edc_parser.py                # инкрементальный (без телефонов)
  ./bin/python edc_parser.py --max-pages 2  # тест
  ./bin/python edc_parser.py --full
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
DEFAULT_OUT = HERE / "edc_realty.xlsx"
BASE = "https://edc.sale"
SOURCE = "edc.sale"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
CHECKPOINT_EVERY = 100
CATEGORIES = [("sale", "Продажа"), ("rent", "Аренда")]
# слово-тип в "Продажа зданий"/"Аренда офиса" → наш тип объекта
TYPE_MAP = {"здани": "Здание", "офис": "Офис", "торг": "Торговое", "магазин": "Торговое",
            "склад": "Склад", "производ": "Производство", "помещен": "Помещение",
            "участ": "Участок", "гараж": "Гараж", "кафе": "Общепит", "ресторан": "Общепит"}


def fetch(url: str, retries: int = 3) -> str:
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept-Language": "ru-RU,ru;q=0.9",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * attempt)
    print(f"    ✖ fetch {url}: {last} (под VPN edc недоступен — нужен бел. IP)")
    return ""


def _clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", _html.unescape(s)).strip()


def split_cards(page_html: str) -> list[str]:
    parts = page_html.split("j-item it-list-item")
    return ["j-item it-list-item" + p for p in parts[1:]]


def _grab(card: str, cls: str) -> str:
    return _clean((re.search(r'class="' + re.escape(cls) + r'"[^>]*>(.*?)</div', card, re.S)
                   or [None, ""])[1])


def classify(cat_text: str, deal: str) -> tuple[str, str]:
    """'Продажа зданий' → (тип объекта). deal берём из категории URL."""
    low = cat_text.lower()
    for key, val in TYPE_MAP.items():
        if key in low:
            return val
    return "Помещение"


def parse_card(card: str, deal: str) -> Optional[dict]:
    idm = re.search(r'data-id="(\d+)"', card)
    urlm = re.search(r'href="(https://edc\.sale/[^"]+\.html)"', card)
    if not idm or not urlm:
        return None
    url = urlm.group(1)
    title = _grab(card, "it-item-title c-shadow-overflow")
    address = _grab(card, "it-item-address c-shadow-overflow")
    price = _grab(card, "price-item")
    cat_text = _grab(card, "it-list-item-cat")
    type_ = classify(cat_text, deal)

    imgs = [u for u in re.findall(r'<img class="it-img" src="([^"]+)"', card) if "def-m.svg" not in u]
    photo_urls = ";".join(dict.fromkeys(imgs))

    # площадь из заголовка/описания: «120 м2», «53.3 кв.м», «6 соток»
    blob = _clean(card)
    am = re.search(r"(\d+[.,]?\d*)\s*(?:м2|м²|кв\.?\s*м)", blob)
    area = am.group(1).replace(",", ".") if am else ""

    desc = _grab(card, "")  # описание-див без класса между title и price
    dm = re.search(r"</div>\s*<div>([^<]{15,})</div>\s*<div class=\"it-price-box", card)
    desc = _clean(dm.group(1)) if dm else ""

    final_type = "Здание" if R.is_building_text(title + " " + desc) else type_
    feats = R.parse_features(title + " " + desc, desc)
    h = R.hashlib.md5((R.normalize_url(url) + title + address + price).encode()).hexdigest()[:12]

    item = {c: "н/у" for c in R.COLUMNS}
    item.update({
        "Тип": final_type,
        "Адрес": title or address,
        "Район / Город": address,
        "Площадь, м²": area,
        "Цена общая": price,
        "Цена за м²": "",
        "Описание": R.clean_description(desc),
        "Класс здания": feats["building_class"], "НДС": feats["nds"],
        "Парковка": feats["parking"], "Отдельный вход": feats["separate_entrance"],
        "Мокрая зона": feats["wet_zone"], "Высота потолков, м": feats["ceiling_height"],
        "Грузовая рампа / ворота": feats["ramp_gate"], "Витринные окна / 1-я линия": feats["showcase"],
        "Мин. срок аренды": feats["min_rent"],
        "Контакт": "", "Имя контакта": "",
        "Телефон": "",  # TODO: за JS (j-c-phones), реверс как у kufar
        "Ссылка": url, "Дата публикации": "", "Источник": SOURCE,
        "Сохранить": "", "Фото URL": photo_urls, "Координаты": "",
        "Хэш": h, "_deal": deal,
    })
    return item


def scrape_category(deal_path: str, deal: str, prev_urls: set, cfg) -> list[dict]:
    print(f"\n→ {deal}: /ru/by/real-estate/commercial/{deal_path}")
    results: list[dict] = []
    for page_n in range(1, cfg.max_pages + 1):
        url = f"{BASE}/ru/by/real-estate/commercial/{deal_path}/?lt=list" + (f"&page={page_n}" if page_n > 1 else "")
        page_html = fetch(url)
        if not page_html:
            break
        items = [parse_card(c, deal) for c in split_cards(page_html)]
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
    return results


def main() -> None:
    p = argparse.ArgumentParser(description="Скрейпер edc.sale (коммерция РБ) → Excel. БЕЗ VPN!")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--max-pages", type=int, default=100)
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

    print(f"🚀 edc_parser (БЕЗ VPN!). Дата: {date.today():%d.%m.%Y}")
    print(f"   режим: {'ПОЛНЫЙ' if cfg.full else 'инкрементальный'} | БД {len(prev_db)} | out={cfg.out}")

    all_new: list[dict] = []
    for deal_path, deal in CATEGORIES:
        items = scrape_category(deal_path, deal, prev_urls, cfg)
        all_new.extend(it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls)
        if len(all_new) >= CHECKPOINT_EVERY:
            base = [] if cfg.full else list(prev_db.values())
            R.write_excel(base + all_new, cfg.out, prev_hashes=snapshot)
            print(f"    💾 чекпойнт: {len(all_new)} новых")
        time.sleep(random.uniform(2.0, 4.0))

    base = [] if cfg.full else list(prev_db.values())
    final = base + all_new
    print(f"\n📦 Итог: {len(final)} (новых: {len(all_new)}, из БД: {len(final)-len(all_new)})")
    R.write_excel(final, cfg.out, prev_hashes=snapshot)


if __name__ == "__main__":
    main()

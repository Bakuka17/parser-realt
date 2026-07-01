"""gohome_parser — скрейпер gohome.by (коммерция) → Excel (схема как у realt.by).

gohome отдаёт серверный HTML. В ЛИСТИНГЕ сразу есть всё для обзвона: тип, адрес, город,
площадь, цена (BYN + $/€), ТЕЛЕФОН (tel:, 50/50) и фото — детальные страницы НЕ нужны
(как megapolis). Координаты лежат на деталке /ads/view/{id} ("latitude"/"longitude") —
по флагу --coords (по умолчанию выкл: адрес есть, save_marked геокодит сам).
Переиспользует машинерию realty_parser_v8 (write_excel, load_prev_db, инкрементал, чекпойнты).

Каркас сгенерирован GLM (z.ai) по брифу; на живых данных Claude выловил и пофиксил:
split карточек (бот резал по 1-му </div> → терял цену/фото); сделка из категории, не из alt;
цена в ЕВРО (€=&#8364;) у аренды + неразрывные пробелы в числах рвали BYN; телефон есть
в листинге (детальный проход за ним не нужен); «договорная» вместо пустой цены.

Запуск:
  ./bin/python gohome_parser.py                  # инкрементальный (телефоны из листинга)
  ./bin/python gohome_parser.py --max-pages 2    # ограничить глубину (тест)
  ./bin/python gohome_parser.py --coords         # + координаты с деталок (медленно)
  ./bin/python gohome_parser.py --full           # полный перепрогон
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
DEFAULT_OUT = HERE / "gohome_realty.xlsx"
BASE = "https://gohome.by"
SOURCE = "gohome.by"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
CHECKPOINT_EVERY = 200

CATEGORIES = [("sale", "Продажа"), ("rent", "Аренда")]


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


def split_cards(page_html: str) -> list[str]:
    """Карточки идут подряд; режем от одной w-object-list-item до следующей.
    (Резать по </div> нельзя — карточка содержит десятки вложенных div.)"""
    idx = [m.start() for m in re.finditer(r'<div class="w-object-list-item\b', page_html)]
    out = []
    for i, start in enumerate(idx):
        end = idx[i + 1] if i + 1 < len(idx) else page_html.find("</footer>", start)
        out.append(page_html[start:end if end > 0 else start + 12000])
    return out


def parse_prices(frag: str) -> tuple[str, str]:
    """(Цена общая, Цена за м²). Валюты руб/$/€; неразрывные пробелы нормализуем.
    Возвращает 'X р. / Y $' (или €). Если только «договорная» — обрабатывается выше."""
    s = _html.unescape(frag)
    for sp in ("\xa0", " ", " "):
        s = s.replace(sp, " ")
    total, per = [], []
    for m in re.finditer(r">\s*(?:≈)?\s*([\d][\d .,]*?)\s*(руб/м[²2]|руб|\$/м[²2]|\$|€/м[²2]|€)\s*<", s):
        num = re.sub(r"\s+", " ", m.group(1)).strip()
        unit = m.group(2)
        if not re.search(r"\d", num):
            continue
        cur = "р." if "руб" in unit else ("$" if "$" in unit else "€")
        if "/м" in unit:
            v = f"{num} {cur}/м²"
            if v not in per:
                per.append(v)
        else:
            v = f"{num} {cur}"
            if v not in total:
                total.append(v)
    return " / ".join(total[:2]), " / ".join(per[:2])


def parse_phone(frag: str) -> str:
    tels = re.findall(r"tel:(\+?375\d{9})", frag)
    if not tels:
        raw = re.findall(r"\+375[\s()\-]*\d{2}[\s()\-]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}", frag)
        tels = [re.sub(r"[\s()\-]", "", r) for r in raw]
    return ", ".join(dict.fromkeys("+" + t.lstrip("+") for t in tels[:3]))


def parse_listing_item(frag: str, deal: str) -> Optional[dict]:
    """Карточка листинга → dict. deal («Продажа»/«Аренда») берём из КАТЕГОРИИ."""
    id_m = re.search(r'data-object-id="(\d+)"', frag)
    if not id_m:
        return None
    url = f"{BASE}/ads/view/{id_m.group(1)}"

    # сводка объекта в alt фото: "{Сделка} {тип}, {город}, {адрес}, {площадь} кв.м.. Фото N"
    alt_m = re.search(r'<img[^>]+alt="([^"]+кв\.м[^"]*)"', frag)
    if not alt_m:
        return None
    title = re.sub(r"\.?\s*Фото\s*\d+.*$", "", _html.unescape(alt_m.group(1))).strip()
    parts = [p.strip() for p in title.split(",") if p.strip()]
    if len(parts) < 3:
        return None
    obj_type = " ".join(parts[0].split()[1:]) or parts[0]  # убрать слово сделки
    city = parts[1]
    address = ", ".join(parts[2:-1])
    area_m = re.search(r"([\d.]+)\s*кв\.м", parts[-1])
    area = area_m.group(1) if area_m else ""

    price_total, price_per = parse_prices(frag)
    if not price_total and re.search(r"оговорн", frag):
        price_total = "договорная"

    imgs = re.findall(r'(?:src|srcset)="(/thumbs/[^"]+\.(?:jpg|jpeg|png|webp))"', frag)
    photo_urls = ";".join(dict.fromkeys(f"{BASE}{u}" for u in imgs))

    final_type = "Здание" if R.is_building_text(title) else obj_type
    h = R.hashlib.md5((R.normalize_url(url) + address + area + price_total).encode()).hexdigest()[:12]

    item = {c: "н/у" for c in R.COLUMNS}
    item.update({
        "Тип": final_type,
        "Адрес": address or title[:60],
        "Район / Город": f"г. {city}" if city else "",
        "Площадь, м²": area,
        "Цена общая": price_total,
        "Цена за м²": price_per,
        "Описание": "",
        "Контакт": "", "Имя контакта": "",
        "Телефон": parse_phone(frag),
        "Ссылка": url,
        "Дата публикации": "",
        "Источник": SOURCE,
        "Сохранить": "",
        "Фото URL": photo_urls,
        "Координаты": "",
        "Хэш": h,
        "_deal": deal,
    })
    return item


def fetch_coords(url: str) -> str:
    """Координаты с деталки /ads/view/{id} ("latitude":"…","longitude":"…")."""
    d = fetch(url)
    c = re.search(r'"latitude":"?([\d.]+)"?.*?"longitude":"?([\d.]+)"?', d, re.S)
    return f"{c.group(1)},{c.group(2)}" if c else ""


def scrape_category(deal_path: str, deal: str, prev_urls: set,
                    last_run: Optional[date], cfg) -> list[dict]:
    print(f"\n→ {deal}: /commerce/{deal_path}")
    results: list[dict] = []
    for page_n in range(1, cfg.max_pages + 1):
        url = f"{BASE}/commerce/{deal_path}" + (f"?page={page_n}" if page_n > 1 else "")
        page_html = fetch(url)
        if not page_html:
            break
        items = [parse_listing_item(f, deal) for f in split_cards(page_html)]
        items = [it for it in items if it]
        if not items:
            print(f"  стр.{page_n}: 0 объявлений → стоп")
            break
        new_items = [it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls]
        all_known = bool(prev_urls) and not new_items and not cfg.full
        print(f"  стр.{page_n}: всего {len(items)} | новых {len(new_items)} | известных {len(items)-len(new_items)}"
              + (" | ALL_KNOWN" if all_known else ""))
        results.extend(items)
        if all_known:
            break
        time.sleep(random.uniform(2.0, 4.0))

    if cfg.coords:  # опц. добор координат с деталок (только новые)
        todo = [it for it in results if R.normalize_url(it["Ссылка"]) not in prev_urls]
        print(f"  → координаты {len(todo)} новых…")
        for i, it in enumerate(todo, 1):
            it["Координаты"] = fetch_coords(it["Ссылка"])
            time.sleep(random.uniform(1.5, 3.0))
    print(f"  ✓ из категории: {len(results)}")
    return results


def main() -> None:
    p = argparse.ArgumentParser(description="Скрейпер gohome.by (коммерция) → Excel.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--max-pages", type=int, default=100)
    p.add_argument("--full", action="store_true", help="полный перепрогон")
    p.add_argument("--coords", action="store_true", help="добрать координаты с деталок (медленно)")
    cfg = p.parse_args()
    cfg.out = cfg.out.expanduser().resolve()

    prev_db, last_run = R.load_prev_db(cfg.out)
    prev_urls = set() if cfg.full else set(prev_db.keys())
    snapshot: dict = {}
    for _u, _r in prev_db.items():
        d, hsh = _r.get("_deal"), _r.get("Хэш")
        if d and hsh:
            snapshot.setdefault(d, set()).add(str(hsh))

    print(f"🚀 gohome_parser. Дата: {date.today():%d.%m.%Y}")
    print(f"   режим: {'ПОЛНЫЙ' if cfg.full else 'инкрементальный'} | БД {len(prev_db)} | out={cfg.out}")

    all_new: list[dict] = []
    for ci, (deal_path, deal) in enumerate(CATEGORIES):
        if ci:
            time.sleep(random.uniform(4.0, 8.0))
        items = scrape_category(deal_path, deal, prev_urls, last_run, cfg)
        all_new.extend(it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls)
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

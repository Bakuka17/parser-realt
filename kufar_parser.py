"""kufar_parser — скрейпер re.kufar.by → Excel (схема как у realt.by).

Kufar — Next.js-сайт: все данные лежат в <script id="__NEXT_DATA__"> как чистый JSON
(props.initialState.listing.ads). Парсим JSON, а не HTML. Структурные фичи
(парковка, отдельный вход, санузел, состояние) приходят готовыми в ad_parameters.

Слабое место: телефоны скрыты за отдельным API-кликом — пока не извлекаются (TODO).

Запуск:
  ./bin/python kufar_parser.py                  # инкрементальный, Минск
  ./bin/python kufar_parser.py --city belarus   # вся Беларусь
  ./bin/python kufar_parser.py --max-pages 5
  ./bin/python kufar_parser.py --full
"""
from __future__ import annotations

import argparse
import json
import random
import re
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import realty_parser_v8 as R

HERE = Path(__file__).parent
DEFAULT_OUT = HERE / "kufar_realty.xlsx"
SOURCE = "kufar.by"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
CHECKPOINT_EVERY = 200

# (фрагмент сделки в URL, тип сделки)
DEALS = [("snyat", "Аренда"), ("kupit", "Продажа")]


def fetch(url: str, retries: int = 3) -> str:
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * attempt)
    print(f"    ✖ fetch {url}: {last}")
    return ""


def extract_next_data(html: str) -> Optional[dict]:
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def get_param(ad: dict, name: str, which: str = "ad_parameters") -> Optional[dict]:
    for p in ad.get(which) or []:
        if p.get("p") == name:
            return p
    return None


def pval(ad: dict, name: str, which: str = "ad_parameters", use_label: bool = True):
    p = get_param(ad, name, which)
    if not p:
        return None
    return p.get("vl") if use_label and p.get("vl") not in (None, "") else p.get("v")


def map_type(label: str) -> Optional[str]:
    l = (label or "").lower()
    if "офис" in l:
        return "Офис"
    if "склад" in l:
        return "Склад"
    if "производ" in l:
        return "Производство"
    if "торгов" in l or "магазин" in l:
        return "Торговое"
    if "кафе" in l or "бар" in l or "ресторан" in l or "общепит" in l or "общеп" in l:
        return "Общепит"
    if "здани" in l or "отдельно стоящ" in l:
        return "Здание"
    return None


def parse_date(iso: str) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d.%m.%Y")
    except ValueError:
        return ""


def parse_ad(ad: dict, deal: str) -> Optional[dict]:
    # Канонический URL по стабильному ad_id (ad_link приходит в двух форматах —
    # короткий /vi/{id} и полный /vi/{город}/.../{id} — что ломает дедуп по URL).
    ad_id = ad.get("ad_id") or ad.get("list_id")
    if ad_id:
        url = f"https://re.kufar.by/vi/{ad_id}"
    else:
        url = ad.get("ad_link") or ""
    if not url:
        return None

    subject = ad.get("subject") or ""
    body = ad.get("body_short") or ad.get("body") or ""
    # цена: price_byn/usd в копейках
    byn = ad.get("price_byn")
    usd = ad.get("price_usd")
    price_parts = []
    if byn and str(byn).isdigit():
        price_parts.append(f"{int(byn)//100:,}".replace(",", " ") + " р.")
    if usd and str(usd).isdigit():
        price_parts.append(f"{int(usd)//100:,}".replace(",", " ") + " $")
    price_total = " / ".join(price_parts)

    # площадь = параметр «size» («Общая площадь»). НЕ square_meter — то «Цена за м²»!
    area = pval(ad, "size", use_label=False)
    if area in (None, ""):
        area = ""
    else:
        area = str(area)
        if "." in area:  # убираем хвостовые нули только у дробных (31.340 → 31.34)
            area = area.rstrip("0").rstrip(".")
    type_label = pval(ad, "property_type") or ""
    final_type = map_type(type_label) or "Офис"

    address = pval(ad, "address", which="account_parameters") or ""
    name = pval(ad, "name", which="account_parameters") or ""
    region = pval(ad, "region") or ""
    city = "г. " + region if region else ""
    floor = pval(ad, "floor") or ""
    if isinstance(floor, list):
        floor = "/".join(str(x) for x in floor)
    condition = pval(ad, "condition") or "н/у"

    # структурные улучшения (commercial_improvements: список лейблов в vl)
    impr_p = get_param(ad, "commercial_improvements")
    impr_labels = []
    if impr_p:
        vl = impr_p.get("vl")
        if isinstance(vl, list):
            impr_labels = [str(x).lower() for x in vl]
    has = lambda kw: "Да" if any(kw in x for x in impr_labels) else "н/у"  # noqa: E731
    parking = has("парковк")
    entrance = has("отдельн")
    wet = "Да" if any(("сан" in x or "туалет" in x) for x in impr_labels) else "н/у"

    pub_date = parse_date(ad.get("list_time") or "")

    # фото: images[].path → CDN rms.kufar.by — ВСЕ фото из объявления (без лимита).
    # Планировка/кухня/фасад автоматически не различить, поэтому сохраняем всё —
    # пользователь визуально перебирает.
    photo_paths = [im.get("path") for im in (ad.get("images") or []) if im.get("path")]
    photo_urls = ";".join(f"https://rms.kufar.by/v1/gallery/{p}" for p in photo_paths)
    # координаты: coordinates v = [lng, lat] → сохраняем как "lat,lng"
    coords = ""
    cp = get_param(ad, "coordinates")
    if cp and isinstance(cp.get("v"), list) and len(cp["v"]) == 2:
        lng, lat = cp["v"]
        coords = f"{lat},{lng}"

    # дополним фичи разбором текста (НДС, рампа, потолки, витрина, мин.срок)
    feats = R.parse_features(subject + " " + body, body)
    blob = subject + " " + body
    if R.is_building_text(blob) or map_type(type_label) == "Здание":
        final_type = "Здание"

    h = R.hashlib.md5(
        (R.normalize_url(url) + address + str(area) + price_total).encode()
    ).hexdigest()[:12]

    item = {c: "н/у" for c in R.COLUMNS}
    item.update({
        "Тип": final_type,
        "Адрес": address or subject[:60],
        "Район / Город": city,
        "Площадь, м²": area,
        "Цена общая": price_total,
        "Цена за м²": "",
        "Этаж / этажность": str(floor),
        "Год постройки": "н/у",
        "Класс здания": feats["building_class"],
        "Состояние": condition,
        "НДС": feats["nds"],
        "Парковка": parking,
        "Отдельный вход": entrance,
        "Мокрая зона": wet,
        "Контакт": "Агентство" if ad.get("company_ad") else "Собственник / Частное лицо",
        "Имя контакта": name if name.lower() != "продавец" else "",
        "Телефон": "",  # скрыт за API Kufar — TODO
        "Ссылка": url,
        "Дата публикации": pub_date,
        "Источник": SOURCE,
        "Высота потолков, м": feats["ceiling_height"],
        "Грузовая рампа / ворота": feats["ramp_gate"],
        "Электр. мощность, кВт": "н/у",
        "Витринные окна / 1-я линия": feats["showcase"],
        "Мин. срок аренды": feats["min_rent"],
        "Материал стен": "н/у",
        "Описание": R.clean_description(body),
        "Сохранить": "",
        "Фото URL": photo_urls,
        "Координаты": coords,
        "Хэш": h,
        "_deal": deal,
    })
    return item


def next_token(listing: dict) -> Optional[str]:
    for pg in listing.get("pagination") or []:
        if pg.get("label") == "next" and pg.get("token"):
            return pg["token"]
    return None


def scrape_deal(city: str, deal_frag: str, deal: str, prev_urls: set,
                last_run: Optional[date], cfg) -> list[dict]:
    base = f"https://re.kufar.by/l/{city}/{deal_frag}/kommercheskaya"
    print(f"\n→ {deal}: {base}")
    results: list[dict] = []
    cursor = None
    for page_n in range(1, cfg.max_pages + 1):
        url = base + (f"?cursor={cursor}" if cursor else "")
        html = fetch(url)
        data = extract_next_data(html)
        if not data:
            print(f"  стр.{page_n}: нет __NEXT_DATA__ → стоп")
            break
        listing = data["props"]["initialState"]["listing"]
        ads = listing.get("ads") or []
        if not ads:
            print(f"  стр.{page_n}: 0 объявлений → стоп")
            break
        items = [parse_ad(a, deal) for a in ads]
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
        cursor = next_token(listing)
        if not cursor:
            print(f"  стр.{page_n}: конец пагинации")
            break
        time.sleep(random.uniform(2.0, 4.0))  # щадящая пауза против бана
    print(f"  ✓ из сделки: {len(results)}")
    return results


def main() -> None:
    p = argparse.ArgumentParser(description="Скрейпер re.kufar.by → Excel.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--city", default="minsk", help="minsk | belarus | gomel ... (по умолч. minsk)")
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

    mode = "ПОЛНЫЙ" if cfg.full else (
        f"инкрементальный (БД {len(prev_db)}"
        + (f", last_run={last_run:%d.%m.%Y}" if last_run else "") + ")"
        if prev_db else "первый прогон")
    print(f"🚀 kufar_parser. Дата: {date.today():%d.%m.%Y} | город: {cfg.city}")
    print(f"   режим: {mode} | out={cfg.out}")

    all_new: list[dict] = []
    for deal_frag, deal in DEALS:
        items = scrape_deal(cfg.city, deal_frag, deal, prev_urls, last_run, cfg)
        new = [it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls]
        all_new.extend(new)
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

"""mgcn_auctions — парсер аукционов Минского городского центра недвижимости (mgcn.by).

Серверный HTML (WordPress). Список: /auctions/{sale,rent,place}/ — карточки с
заголовком + датой + ссылкой на деталь /auction/{slug}/. Детальная страница даёт
начальную цену, задаток, организатора (всегда МГЦН), телефон (госномер).

Запуск:  ./bin/python mgcn_auctions.py            # инкрементально
         ./bin/python mgcn_auctions.py --full      # перепарсить всё
"""
from __future__ import annotations
import argparse, re, time, random
from pathlib import Path
import auctions_common as A

SOURCE = "mgcn.by"
BASE = "https://mgcn.by"
CATEGORIES = [
    ("https://mgcn.by/auctions/sale/", "Продажа с аукциона"),
    ("https://mgcn.by/auctions/rent/", "Аренда с аукциона"),
    ("https://mgcn.by/auctions/place/", "Аренда земли"),
]


def parse_list(html: str) -> list[dict]:
    """Возвращает [{url, title, date_raw}] из страницы списка."""
    out = []
    # режем по маркеру карточки
    parts = html.split('w-auction-list__item')
    for seg in parts[1:]:
        seg = seg[:1500]  # карточка короткая
        link = re.search(r'href="(https://mgcn\.by/auction/[^"]+)"', seg)
        title = re.search(r'<b>(.*?)</b>', seg, re.S)
        dt = re.search(r'<span>\s*([^<]*\d{4})\s*</span>', seg)
        if link and title:
            out.append({
                "url": link.group(1),
                "title": A.clean(title.group(1)),
                "date_raw": dt.group(1).strip() if dt else "",
            })
    return out


def parse_detail(html: str, card: dict, deal_type: str) -> dict:
    it = A.blank_item(SOURCE)
    text = A.clean(html)
    title = card["title"]
    it["Тип торгов"] = "Аукцион"
    it["Объект"] = title
    # дата: из карточки, иначе из текста
    it["Дата аукциона"] = A.parse_date(card.get("date_raw", "")) or A.parse_date(text)
    # начальная цена
    mp = re.search(r"Начальн\w+\s+цен\w+[^.]*?([\d\s]+[.,]?\d*)\s*(?:BYN|бел\.?\s*руб)", text, re.I)
    if mp:
        it["Начальная цена"] = A.parse_price(mp.group(0))
    # задаток (сумма обычно идёт ПОСЛЕ слова, в пределах ~60 симв)
    mz = re.search(r"[Зз]адат\w+.{0,60}?(\d[\d\s]*[.,]?\d*)\s*(?:BYN|бел\.?\s*руб|Br)", text)
    if mz:
        it["Задаток"] = A.parse_price(mz.group(0))
    # организатор
    mo = re.search(r"[Оо]рганизатор[^:]*:\s*([^.]{5,80})", text)
    it["Организатор"] = A.clean(mo.group(1)) if mo else "ГП «МГЦН»"
    # телефон
    it["Телефон"] = A.extract_phones(html)
    # адрес/площадь — общие хелперы (заголовок + текст деталки)
    blob = title + ". " + text[:1500]
    addr = A.extract_address(blob)
    if addr:
        it["Адрес"] = addr
    if re.search(r"минск", blob, re.I):
        it["Район / Город"] = "г. Минск"
    area = A.extract_area(title) or A.extract_area(text[:800])
    if area:
        it["Площадь, м²"] = str(area)
    it["Ссылка"] = A.norm_url(card["url"])
    it["Хэш"] = A.make_hash(it["Ссылка"], it["Объект"])
    return it


def collect(prev_db: dict, full: bool) -> list[dict]:
    prev_urls = set() if full else set(prev_db.keys())
    new = []
    seen = set()
    for list_url, deal in CATEGORIES:
        print(f"\n→ {deal}: {list_url}")
        html = A.fetch(list_url)
        cards = parse_list(html)
        print(f"  карточек: {len(cards)}")
        for card in cards:
            nu = A.norm_url(card["url"])
            if nu in seen:
                continue
            seen.add(nu)
            if nu in prev_urls and not full:
                continue
            dhtml = A.fetch(card["url"])
            if not dhtml:
                continue
            it = parse_detail(dhtml, card, deal)
            new.append(it)
            print(f"  + {it['Дата аукциона'] or '????'} | {it['Объект'][:45]} | {it['Начальная цена'] or '—'}")
            time.sleep(random.uniform(1.0, 2.0))
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=A.DEFAULT_OUT)
    ap.add_argument("--full", action="store_true")
    cfg = ap.parse_args()
    cfg.out = cfg.out.expanduser().resolve()

    prev_db = A.load_prev(cfg.out)
    snapshot = {str(r.get("Хэш")) for r in prev_db.values() if r.get("Хэш")}
    print(f"🔨 mgcn_auctions | БД: {len(prev_db)} | out: {cfg.out.name}")

    new = collect(prev_db, cfg.full)
    final = ([] if cfg.full else list(prev_db.values())) + new
    print(f"\n📦 Итог: {len(final)} (новых: {len(new)})")
    A.write_excel(final, cfg.out, prev_hashes=snapshot)


if __name__ == "__main__":
    main()

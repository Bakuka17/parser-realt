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
from bs4 import BeautifulSoup
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


def mgcn_address(title: str, text: str) -> str:
    """Адрес ОБЪЕКТА (не офиса MGCN!). Каркас DeepSeek, исправлен мной (10/10 + живые):
    приоритет — маркер «расположен… по адресу: …» (режем по «Наш адрес»/футеру, не по
    точке-сокращению), иначе — из заголовка «на ул. X, N в Городе» → «г. Город, ул. X, N»."""
    m = re.search(r"располож\w*\s+по\s+адресу:\s*", text, re.I | re.S)
    if m:
        chunk = text[m.end():m.end() + 140]
        cut = re.search(r"Наш\s+адрес|Как\s+проехать|Реквизит|Телефон", chunk, re.I)
        if cut:
            chunk = chunk[:cut.start()]
        chunk = re.sub(r"\s*\.\s*$", "", chunk.strip()).strip(" .,;")
        if chunk:
            return chunk
    mt = re.search(r"на\s+(ул\.|пр\.|пр-т|просп\.|пер\.|пл\.)\s+([^,]+?)\s*,?\s*"
                   r"(\d+[А-Яа-я]?)\s+в\s+([А-Яа-я]+)", title, re.I)
    if mt:
        cmap = {"Минске": "Минск", "Гомеле": "Гомель", "Бресте": "Брест",
                "Витебске": "Витебск", "Могилёве": "Могилёв", "Гродно": "Гродно"}
        city = cmap.get(mt.group(4).strip().rstrip("."), mt.group(4).strip().rstrip("."))
        return f"г. {city}, {mt.group(1)} {mt.group(2).strip()}, {mt.group(3)}"
    return ""


def mgcn_area(title: str, text: str):
    """Площадь объекта в м² (float) из заголовка/текста; гектары (га) не берёт."""
    pat = re.compile(r"(?:площадью\s+)?(\d[\d\s]*[.,]?\d*)\s*(?:кв\.?\s*м|м2|м²)", re.I)
    for s in (title, text):
        mt = pat.search(s)
        if mt:
            try:
                return float(re.sub(r"\s", "", mt.group(1)).replace(",", "."))
            except ValueError:
                pass
    return None


def _table_money_range(html: str, match) -> str:
    """Диапазон сумм из колонки HTML-таблицы, чья ячейка-шапка проходит match(text_lower).
    У mgcn многолотовые аукционы — таблица, где у КАЖДОГО лота своя строка; шапка часто
    во ВТОРОЙ строке (первая — colspan «Сведения о…»), поэтому сканируем все строки.
    Среди подошедших шапок приоритет «…предмета аукциона» (итог с НДС, а не отдельно
    квартира/машино-место). Возвращает 'lo–hi BYN' (или 'n BYN' при одном лоте), либо ''."""
    vals: list[float] = []
    soup = BeautifulSoup(html, "lxml")
    for tbl in soup.find_all("table"):
        rows = [tr.find_all(["td", "th"]) for tr in tbl.find_all("tr")]
        hdr_row = hdr_col = None
        best = 99
        for ri, cells in enumerate(rows):
            for ci, c in enumerate(cells):
                t = re.sub(r"\s+", " ", c.get_text(" ", strip=True)).lower()
                if match(t):
                    score = 0 if ("предмет" in t and "аукцион" in t) else 1
                    if score < best:
                        best, hdr_row, hdr_col = score, ri, ci
        if hdr_row is None:
            continue
        for cells in rows[hdr_row + 1:]:
            if len(cells) <= hdr_col:
                continue
            p = A.parse_price(cells[hdr_col].get_text(" ", strip=True))
            if p:
                try:
                    n = float(p.split()[0])
                    if n > 500:  # отсечь проценты/копейки/мусор
                        vals.append(n)
                except ValueError:
                    pass
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    return f"{lo:.0f} BYN" if lo == hi else f"{lo:.0f}–{hi:.0f} BYN"


def mgcn_price(html: str, text: str) -> str:
    """Начальная цена: одиночный лот — проза («Начальная цена …: 1 896 000,0 бел. руб.»);
    многолотовый — диапазон по колонке «Начальная цена…» из таблицы."""
    return A.extract_start_price(text) or _table_money_range(
        html, lambda t: "начальн" in t and "цен" in t)


def mgcn_deposit(html: str, text: str) -> str:
    """Задаток: многолотовый — диапазон по колонке «Размер задатка»; фолбэк — проза."""
    r = _table_money_range(html, lambda t: "задат" in t)
    if r:
        return r
    m = re.search(r"[Зз]адат\w+.{0,60}?(\d[\d\s]*[.,]?\d*)\s*(?:BYN|бел\.?\s*руб|Br)", text)
    return A.parse_price(m.group(0)) if m else ""


def parse_detail(html: str, card: dict, deal_type: str) -> dict:
    it = A.blank_item(SOURCE)
    text = A.clean(html)
    title = card["title"]
    it["Тип торгов"] = "Аукцион"
    it["Объект"] = title
    # дата: из карточки, иначе из текста
    it["Дата аукциона"] = A.parse_date(card.get("date_raw", "")) or A.parse_date(text)
    # начальная цена: проза (одиночный лот) → таблица многолотового аукциона (диапазон)
    it["Начальная цена"] = mgcn_price(html, text)
    # задаток: таблица многолотового аукциона (колонка «Размер задатка») → проза
    it["Задаток"] = mgcn_deposit(html, text)
    # организатор у mgcn — ВСЕГДА сам центр (МГЦН). Regex иногда ловит мусор из текста
    # («документ», «электроснабжение» и т.п. — было 33% брака) → если в захвате нет
    # «МГЦН», берём канон. Имя до «…», без адреса офиса (улучшено vs Qwen).
    mo = re.search(r"[Оо]рганизатор[^:]*:\s*([^.,\n]*«[^»]+»|[^.,\n]{5,70})", text)
    org = A.clean(mo.group(1)) if mo else ""
    it["Организатор"] = org if "МГЦН" in org else "государственное предприятие «МГЦН»"
    # телефон: A.extract_phones возвращает СТРОКУ; фолбэк «Телефон: …» (идея Qwen,
    # но БЕЗ его бага ", ".join(строка) — это рвало номер по символам)
    phones = A.extract_phones(html)
    if not phones:
        pm = re.search(r"(?:Телефон|Тел\.|Контактный телефон)[^:]*:\s*(\+?\d[\d\s\-()]{7,20})",
                       text, re.I)
        if pm:
            phones = A.clean(pm.group(1))
    it["Телефон"] = phones
    # адрес/площадь — mgcn-специфичные (А.extract_address брал ОФИС фирмы)
    addr = mgcn_address(title, text)
    it["Адрес"] = addr
    mcity = re.search(r"г\.\s*([А-ЯЁ][а-яё-]+)", addr)
    if mcity:
        it["Район / Город"] = "г. " + mcity.group(1)
    elif re.search(r"минск", title, re.I):
        it["Район / Город"] = "г. Минск"
    area = mgcn_area(title, text)
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
    ap.add_argument("--out", type=Path, default=Path("auctions_mgcn.xlsx"))
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

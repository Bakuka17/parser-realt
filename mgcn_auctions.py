"""mgcn_auctions — парсер аукционов Минского городского центра недвижимости (mgcn.by).

Серверный HTML (WordPress). Список: /auctions/{sale,rent,place}/ — карточки с
заголовком + датой + ссылкой на деталь /auction/{slug}/. Детальная страница даёт
начальную цену, задаток, организатора (всегда МГЦН), телефон (госномер).

Запуск:  ./bin/python mgcn_auctions.py            # инкрементально
         ./bin/python mgcn_auctions.py --full      # перепарсить всё
"""
from __future__ import annotations
import argparse, os, re, time, random
from collections import Counter
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


_ADDR_RE = re.compile(
    r"(?:г\.?\s*([А-ЯЁ][а-яё-]+)\s*,?\s*)?"                 # необяз. город
    r"(ул|пр-т|просп|пр|пер|пл|бул)\.?\s+"                  # тип улицы
    r"([А-ЯЁ][А-Яа-яё .\-]{2,30}?)\s*,?\s*"                 # название (ленивое)
    r"(\d+[А-Яа-я]?(?:/\d+[А-Яа-я]?)*)(?:-\d+[А-Яа-я]?)?",  # дом (с / для комплексов); кв. отбрасываем
    re.I,
)
_ST_TYPE = {"ул": "ул.", "пр": "пр.", "пр-т": "пр-т", "просп": "просп.",
            "пер": "пер.", "пл": "пл.", "бул": "бул."}
_CITY_GEN = {"минске": "Минск", "гомеле": "Гомель", "бресте": "Брест",
             "витебске": "Витебск", "могилёве": "Могилёв", "могилеве": "Могилёв",
             "гродно": "Гродно"}


def mgcn_address(title: str, text: str) -> str:
    """Адрес ОБЪЕКТА (не офиса МГЦН!). Тянем чистый «[г. Город,] ул. Улица, Дом» регэкспом
    из заголовка+текста: квартиру отбрасываем (дом-уровень), офис МГЦН (К. Маркса, 39)
    исключаем. Для многолотовых берём САМЫЙ ЧАСТЫЙ адрес — доминирующее здание комплекса.
    (Раньше брали 140 симв после «расположен по адресу» → пусто на 70% + мусорные хвосты.)"""
    found: list[tuple[str | None, str]] = []
    for src in (title, text):
        for m in _ADDR_RE.finditer(src):
            city, st, name, house = m.groups()
            name = re.sub(r"\s+", " ", name).strip(" .,-")
            if "маркса" in name.lower() and house.startswith("39"):
                continue  # офис МГЦН, не объект
            core = f"{_ST_TYPE.get(st.lower().rstrip('.'), 'ул.')} {name}, {house}"
            found.append((city.strip() if city else None, core))
    if not found:
        return ""
    top_core = Counter(c for _, c in found).most_common(1)[0][0]
    cities = [c for c, core in found if core == top_core and c]
    city = cities[0] if cities else None
    if not city:
        tm = re.search(r"в\s+([А-ЯЁ][а-яё]+е)\b", title)
        if tm:
            city = _CITY_GEN.get(tm.group(1).lower())
    return f"г. {city}, {top_core}" if city else top_core


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
        for ri, cells in enumerate(rows[:3]):  # шапка только в первых строках (не в дата-ячейках!)
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
            cell_txt = cells[hdr_col].get_text(" ", strip=True)
            if "%" in cell_txt or "процент" in cell_txt.lower():
                continue  # это шаг/процент, не цена
            p = A.parse_price(cell_txt)
            if p:
                try:
                    n = float(p.split()[0])
                    if n >= 50:  # легит лизинг-цены ≥60 BYN; <50 — мусор (номера лотов/мелочь)
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
    # категория листинга: «Продажа с аукциона» / «Аренда с аукциона» / «Аренда земли»
    it["Тип торгов"] = deal_type or "Аукцион"
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


CHECKPOINT_EVERY = 20  # сохранять прогресс каждые N собранных лотов (защита от обрыва)


def collect(skip_urls: set, on_checkpoint=None) -> list[dict]:
    """Собирает деталь по всем категориям, пропуская URL из skip_urls (уже собранные —
    для инкремента И для резюма после обрыва). on_checkpoint(new) — периодический сейв."""
    new = []
    seen = set()
    for list_url, deal in CATEGORIES:
        print(f"\n→ {deal}: {list_url}")
        html = A.fetch(list_url)
        cards = parse_list(html)
        print(f"  карточек: {len(cards)}")
        for card in cards:
            nu = A.norm_url(card["url"])
            if nu in seen or nu in skip_urls:
                continue
            seen.add(nu)
            dhtml = A.fetch(card["url"])
            if not dhtml:
                continue
            it = parse_detail(dhtml, card, deal)
            new.append(it)
            print(f"  + {it['Дата аукциона'] or '????'} | {it['Объект'][:45]} | {it['Начальная цена'] or '—'}")
            if on_checkpoint and len(new) % CHECKPOINT_EVERY == 0:
                on_checkpoint(new)
            time.sleep(random.uniform(1.0, 2.0))
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("auctions_mgcn.xlsx"))
    ap.add_argument("--full", action="store_true")
    cfg = ap.parse_args()
    cfg.out = cfg.out.expanduser().resolve()

    tmp = cfg.out.with_suffix(".tmp.xlsx")  # незавершённый чекпойнт

    # База для дедупа/резюма:
    #  • инкремент → читаем готовый out;
    #  • --full → начинаем с нуля, НО если остался .tmp от обрыва — продолжаем с него (резюм).
    if cfg.full:
        base = A.load_prev(tmp) if tmp.exists() else {}
        if base:
            print(f"♻ найден незавершённый --full чекпойнт ({len(base)} лотов) — продолжаю с него")
    else:
        base = A.load_prev(cfg.out)
    base_vals = list(base.values())
    skip_urls = set(base.keys())
    snapshot = {str(r.get("Хэш")) for r in base.values() if r.get("Хэш")}
    print(f"🔨 mgcn_auctions | БД: {len(base)} | out: {cfg.out.name}")

    def save(items: list[dict], tag: str = "") -> None:
        """Атомарная запись: пишем в .tmp, затем переименовываем в out."""
        A.write_excel(base_vals + items, tmp, prev_hashes=snapshot)
        if tag == "final":
            os.replace(tmp, cfg.out)
        else:
            print(f"  💾 чекпойнт: всего {len(base_vals) + len(items)} (новых {len(items)})")

    new = collect(skip_urls, on_checkpoint=lambda items: save(items))
    print(f"\n📦 Итог: {len(base_vals) + len(new)} (новых: {len(new)})")
    save(new, tag="final")


if __name__ == "__main__":
    main()

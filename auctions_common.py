"""auctions_common — общий каркас для парсеров аукционных площадок РБ.

Все парсеры аукционов (mgcn, e-auction, torgi24, ...) импортируют отсюда:
  • схему колонок AUCTION_COLUMNS;
  • fetch() — загрузка с браузерным UA и ретраями;
  • parse_price() / parse_date() — нормализация (правила цены/дат);
  • make_hash(), write_excel(), load_prev() — дедуп по URL + инкрементал + чекпойнты.

Пишут в auctions_realty.xlsx, лист «Аукционы». Отдельно от commercial_realty.xlsx
(другая природа: торги, а не прямые объявления). Слияние — позже, при необходимости.
"""
from __future__ import annotations

import hashlib
import re
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill, Side, Border
from openpyxl.utils import get_column_letter

HERE = Path(__file__).parent
DEFAULT_OUT = HERE / "auctions_realty.xlsx"
SHEET = "Аукционы"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

AUCTION_COLUMNS = [
    "Сохранить",
    "Тип торгов",        # аукцион / конкурс / электронные торги
    "Тип объекта",       # авто из заголовка: Офис/Склад/Земля/... (заполняет write_excel)
    "Объект",            # заголовок лота
    "Адрес",
    "Район / Город",
    "Площадь, м²",
    "Начальная цена",
    "Задаток",
    "Дата аукциона",     # YYYY-MM-DD
    "Организатор",
    "Телефон",
    "Ссылка",
    "Источник",
    "Фото URL",
    "Хэш",
]

# ── нормализация цены ────────────────────────────────────────────────────────
_CUR = [
    (re.compile(r"\bBYN\b|бел\.?\s*руб|белорусск\w*\s*рубл|\bBr\b", re.I), "BYN"),
    (re.compile(r"\bUSD\b|\$|долл", re.I), "USD"),
    (re.compile(r"\bEUR\b|€|евро", re.I), "EUR"),
    (re.compile(r"\bRUB\b|рос\.?\s*руб|россий\w*\s*рубл", re.I), "RUB"),
]


def extract_start_price(text: str) -> str:
    """Прицельно вытащить НАЧАЛЬНУЮ цену из текста деталки (схлопывает пробелы/переносы).
    Ловит 'Начальная цена: 945856.58 бел.руб', 'Стартовая цена ... 100 000 BYN'."""
    if not text:
        return ""
    t = re.sub(r"[\s\xa0]+", " ", text.replace("&nbsp;", " "))
    m = re.search(
        r"(?:начальн\w*|стартов\w*)\s+цен\w*[^\d]{0,40}?"
        r"(\d[\d ]*[.,]?\d*)\s*(?:BYN|бел\.?\s*руб|Br|руб)",
        t, re.I,
    )
    if m:
        return parse_price(m.group(0))
    return ""


def parse_price(text: str) -> str:
    """'137 865.03 BYN' → '137865.03 BYN'; '1 250 000 бел. руб.' → '1250000 BYN'."""
    if not text:
        return ""
    cur = ""
    for rx, code in _CUR:
        if rx.search(text):
            cur = code
            break
    # число: цифры, пробелы-разделители тысяч, точка/запятая-десятичная
    m = re.search(r"\d[\d\s]*(?:[.,]\d{1,2})?", text)
    if not m:
        return ""
    num = m.group(0).replace(" ", "").replace(" ", "")
    # запятая как десятичный разделитель → точка
    if "," in num and "." not in num:
        num = num.replace(",", ".")
    else:
        num = num.replace(",", "")
    num = num.rstrip(".")
    if not num or not any(c.isdigit() for c in num):
        return ""
    return f"{num} {cur}".strip()


# ── нормализация дат ─────────────────────────────────────────────────────────
_MONTHS = {
    # русский
    "январ": 1, "феврал": 2, "март": 3, "апрел": 4, "ма": 5, "май": 5, "мая": 5,
    "июн": 6, "июл": 7, "август": 8, "сентябр": 9, "октябр": 10, "ноябр": 11, "декабр": 12,
    # белорусский
    "студзен": 1, "лют": 2, "сакавік": 3, "красавік": 4, "травен": 5, "чэрвен": 6,
    "ліпен": 7, "жнівен": 8, "верасен": 9, "кастрычнік": 10, "лістапад": 11, "снежан": 12,
}


def parse_date(text: str) -> str:
    """'23 июля 2026' / '23.07.2026' / '23 ліпеня 2026' → '2026-07-23'. Иначе ''."""
    if not text:
        return ""
    # DD.MM.YYYY
    m = re.search(r"\b(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{4})\b", text)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return f"{y:04d}-{mo:02d}-{d:02d}"
    # DD месяц YYYY (ru/be)
    m = re.search(r"\b(\d{1,2})\s+([а-яёіў]+)\s+(\d{4})", text, re.I)
    if m:
        d = int(m.group(1)); mon_raw = m.group(2).lower(); y = int(m.group(3))
        mo = None
        for stem, num in _MONTHS.items():
            if mon_raw.startswith(stem):
                mo = num
                break
        if mo:
            return f"{y:04d}-{mo:02d}-{int(d):02d}"
    return ""


# ── площадь / адрес (логика от DeepSeek + фикс префикса области) ──────────────
def extract_area(text: str) -> Optional[float]:
    """Площадь в м² из текста: '1156 кв.м'→1156.0, '90,1 кв. м'→90.1, '1 250,5'→1250.5."""
    if not isinstance(text, str):
        return None
    norm = re.sub(r"\s+", " ", text.strip())
    pat = r"(\d[\d\s]*[.,]?\d*)\s*(?:кв\.?\s*м[²2]?|м[²2]|м\.кв\.|S\s*=\s*(\d[\d\s]*[.,]?\d*))"
    m = re.search(pat, norm, re.IGNORECASE)
    if not m:
        m = re.search(r"(?:площад[ья]|S\s*=)\s*(\d[\d\s]*[.,]?\d*)", norm, re.IGNORECASE)
        if not m:
            return None
    num = m.group(1) if m.group(1) else m.group(2)
    if not num:
        return None
    num = re.sub(r"\s", "", num).replace(",", ".")
    try:
        return float(num)
    except ValueError:
        return None


def extract_address(text: str) -> Optional[str]:
    """Адрес из бел./рус. текста торгов. Возвращает строку или None."""
    if not isinstance(text, str):
        return None
    norm = re.sub(r"\s+", " ", text.strip())
    # 1) [Область обл.,] г. Город, ул./пр./пер. Улица, дом  — захват С названием области
    p1 = (r"((?:[А-ЯЁ][а-яё]+\s+обл\.?,?\s+)?"
          r"г\.\s*[А-ЯЁ][а-яё-]+\s*,?\s+"
          r"(?:ул\.|улица|пр\.|просп\.|проспект|пер\.|пл\.)\s+[А-ЯЁа-яё\-\. ]+?"
          r"\s*,?\s*\d+[А-ЯЁа-яё]*(?:/\d+)?)")
    m = re.search(p1, norm)
    if m:
        return m.group(1).strip().rstrip(",")
    # 2) «в г. Город по ул. Улица, дом» → нормализуем
    m = re.search(r"в\s+г\.\s*([А-ЯЁа-яё-]+)\s+по\s+(ул\.|улица|пр\.|пер\.)\s+([А-ЯЁа-яё\-\. ]+?)\s*,?\s*(\d+[А-ЯЁа-яё]*)", norm, re.IGNORECASE)
    if m:
        return f"г. {m.group(1)}, {m.group(2)} {m.group(3).strip()}, {m.group(4)}"
    # 3) «в городе Город» / «в г. Город» без улицы
    m = re.search(r"(?:в\s+городе|в\s+г\.)\s+([А-ЯЁ][а-яё-]+)", norm)
    if m:
        return m.group(1).strip()
    return None


# ── классификация типа объекта / номер лота (логика от Qwen + фиксы) ──────────
def classify_object_type(title: str) -> str:
    """Тип объекта по заголовку лота. Один из:
    Офис/Торговое/Склад/Производство/Здание/Квартира/Машиноместо/Земля/Иное."""
    t = (title or "").lower()
    # порядок: квартира ВЫШЕ машиноместа («квартиры с машино-местами» → Квартира)
    if re.search(r"квартир|комнат|жил(?:ое|ой|ая|ые)", t):
        return "Квартира"
    if re.search(r"машино|машиноместо|паркинг|парков", t):
        return "Машиноместо"
    if re.search(r"земельн|право\s+аренды\s+земель|земельны\w*\s+участ|\bучаст(?:ок|ка)", t):
        return "Земля"
    if re.search(r"склад|хранилищ", t):
        return "Склад"
    if re.search(r"производ|цех|\bбаза\b|базы", t):
        return "Производство"
    if re.search(r"торгов|магазин|общепит|кафе|ресторан", t):
        return "Торговое"
    if re.search(r"офис|администрат", t):
        return "Офис"
    if re.search(r"здани|строени|сооружени|комплекс", t):
        return "Здание"
    return "Иное"


def extract_lot_number(title: str) -> Optional[str]:
    """Номер аукциона/лота: '№ 05-А-26' → '05-А-26', 'No 15-А' → '15-А'."""
    m = re.search(r"(?:лот\s*)?(?:№|No|N°)\s*([0-9][0-9А-Яа-яёЁA-Za-z\-]*)", title or "", re.I)
    return m.group(1) if m else None


def extract_area_multi(text: str) -> list[float]:
    """Все площади из КОРОТКОГО текста (заголовок/сниппет, НЕ вся страница!).
    '1156 и 334 кв.м' → [1156.0, 334.0]. На полном HTML не использовать — поймает мусор."""
    if not re.search(r"кв\.?\s*м\.?|м[²2]|площад", text or "", re.I):
        return []
    out = []
    for m in re.findall(r"(\d+(?:\s\d{3})*(?:[,.]\d+)?)(?![А-Яа-яёЁ])", text):
        try:
            out.append(float(m.replace(" ", "").replace(",", ".")))
        except ValueError:
            pass
    return out


# ── телефоны / общее ─────────────────────────────────────────────────────────
PHONE_RE = re.compile(r"\+?375[\s\-()]*\d{2}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")


def extract_phones(text: str, limit: int = 3) -> str:
    found = []
    for p in PHONE_RE.findall(text or ""):
        norm = re.sub(r"[^\d+]", "", p)
        if norm not in [re.sub(r"[^\d+]", "", x) for x in found]:
            found.append(p.strip())
        if len(found) >= limit:
            break
    return ", ".join(found)


def make_hash(url: str, *parts: str) -> str:
    raw = (url.split("?")[0].rstrip("/") + "|" + "|".join(parts)).encode()
    return hashlib.md5(raw).hexdigest()[:12]


def fetch(url: str, retries: int = 3, timeout: int = 30) -> str:
    last: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru,be"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * attempt)
    print(f"    ✖ fetch {url}: {last}")
    return ""


def clean(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    import html as _h
    s = _h.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def blank_item(source: str) -> dict:
    it = {c: "" for c in AUCTION_COLUMNS}
    it["Источник"] = source
    return it


# ── чтение/запись xlsx ───────────────────────────────────────────────────────
def load_prev(path: Path) -> dict[str, dict]:
    """{normalized_url: item} из существующего файла (для инкрементала/дедупа)."""
    db: dict[str, dict] = {}
    if not path.exists():
        return db
    try:
        wb = load_workbook(path, data_only=True, read_only=True)
        if SHEET not in wb.sheetnames:
            wb.close(); return db
        ws = wb[SHEET]
        header = None
        for row in ws.iter_rows(values_only=True):
            if header is None:
                if row and "Ссылка" in row and "Хэш" in row:
                    header = list(row)
                continue
            if not any(v is not None for v in row):
                continue
            rec = {header[i]: row[i] for i in range(len(header)) if header[i]}
            url = rec.get("Ссылка")
            if url:
                db[str(url).split("?")[0].rstrip("/")] = rec
        wb.close()
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ не прочитал {path.name}: {e}")
    return db


def norm_url(u: str) -> str:
    return (u or "").split("?")[0].split("#")[0].rstrip("/")


def write_excel(items: list[dict], path: Path, prev_hashes: Optional[set] = None) -> None:
    """Пишет лист «Аукционы». Новые строки (хэш не в prev_hashes) подсвечивает жёлтым.
    Авто-заполняет «Тип объекта» из «Объект», если пусто (централизованно для всех источников)."""
    prev_hashes = prev_hashes or set()
    for it in items:
        if not it.get("Тип объекта") and it.get("Объект"):
            it["Тип объекта"] = classify_object_type(it["Объект"])
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.sheet_view.showGridLines = False
    hdr_font = Font(bold=True, color="FFFFFF", size=11)
    hdr_fill = PatternFill("solid", fgColor="7030A0")
    new_fill = PatternFill("solid", fgColor="FFF2A8")
    thin = Side(style="thin", color="CCCCCC")
    cb = Border(left=thin, right=thin, top=thin, bottom=thin)

    c = ws.cell(1, 1, f"🔨 Аукционы недвижимости — {date.today():%d.%m.%Y}")
    c.font = Font(bold=True, size=14)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(AUCTION_COLUMNS))
    for ci, name in enumerate(AUCTION_COLUMNS, 1):
        cc = ws.cell(2, ci, name)
        cc.font = hdr_font; cc.fill = hdr_fill
        cc.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cc.border = cb
    # сортировка: по дате аукциона (ближайшие сверху), пустые — вниз
    items_sorted = sorted(items, key=lambda x: (x.get("Дата аукциона") or "9999"))
    row = 3
    new_count = 0
    for it in items_sorted:
        is_new = bool(prev_hashes) and str(it.get("Хэш", "")) not in prev_hashes
        if is_new:
            new_count += 1
        for ci, name in enumerate(AUCTION_COLUMNS, 1):
            val = it.get(name, "")
            cc = ws.cell(row, ci, val)
            cc.alignment = Alignment(vertical="top", wrap_text=True)
            cc.border = cb
            if name == "Ссылка" and val:
                cc.hyperlink = val
                cc.font = Font(color="0563C1", underline="single", size=10)
            elif name == "Телефон" and val:
                cc.font = Font(bold=True, color="006100", size=11)
            if is_new and name != "Ссылка":
                cc.fill = new_fill
        row += 1
    ws.freeze_panes = "C3"
    widths = {"Сохранить": 10, "Тип торгов": 14, "Тип объекта": 13, "Объект": 40, "Адрес": 28,
              "Район / Город": 16, "Площадь, м²": 12, "Начальная цена": 16,
              "Задаток": 14, "Дата аукциона": 14, "Организатор": 24, "Телефон": 20,
              "Ссылка": 40, "Источник": 16, "Фото URL": 30, "Хэш": 14}
    for ci, name in enumerate(AUCTION_COLUMNS, 1):
        ws.column_dimensions[get_column_letter(ci)].width = widths.get(name, 14)
    ws.auto_filter.ref = f"A2:{get_column_letter(len(AUCTION_COLUMNS))}{max(row-1,2)}"
    wb.save(path)
    msg = f"✅ {path.name}: всего {len(items)}"
    if prev_hashes:
        msg += f" | 🆕 новых: {new_count}"
    print(msg)

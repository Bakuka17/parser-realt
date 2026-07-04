"""onebv_auctions — госнедвижимость за 1 базовую величину + аукционы облкомитетов.

Источники (⚠ оба НЕ гео-блокированы — проверено под VPN 04.07.2026, гонять можно всегда):
  • Гомель — gomeloblim.gov.by/realty/?price_base=Y (bitrix): листинг с фильтром
    «1 базовая величина» (value=Y!  с =on отдаёт «Ничего не найдено»), пагинация PAGEN_1,
    деталка = 2 таблицы «метка || значение» (цена/задаток во второй).
  • Минобл — minoblim.by/ru/auktsiony (Joomla K2): все аукционы госимущества области
    (не только 1 БВ), пагинация ?start=N (по 16), ссылка деталки в onclick кнопки
    «Подробнее», деталка = пары .auction-single--td. Телефона в лотах нет →
    ставим приёмную комитета.

Выход: auctions_onebv.xlsx (пересборка целиком; merge_auctions подхватит по glob).
Запуск: ./bin/python onebv_auctions.py [--limit N]
"""
from __future__ import annotations

import re
import sys
import time
import urllib.parse
from pathlib import Path

from bs4 import BeautifulSoup

import auctions_common as A

OUT = Path(__file__).parent / "auctions_onebv.xlsx"
PAUSE = 1.0

GOMEL_BASE = "https://gomeloblim.gov.by"
GOMEL_ORG_FALLBACK = "Комитет «Гомельоблимущество»"
MINOBL_BASE = "https://minoblim.by"
MINOBL_ORG = "Комитет госимущества Миноблисполкома"
MINOBL_PHONE = "8 (017) 500-45-01"  # приёмная комитета (minoblim.by/ru/kontakty)

# городские номера госконтор: «тел. (0232) 53-79-26», «(02333) 7-50-60» и +375…
PHONE_RX = re.compile(r"(?:\+375[\d\s()-]{7,}|\(?8?\s?\(?0\d{2,4}\)?\s?[\d-]{5,9}(?:[\s,]|$))")


def _price_byn(text: str) -> str:
    """'45 руб. 00 коп.' → '45 BYN'; '347 000,00 рублей' → '347000 BYN'.
    Госцены всегда BYN, но parse_price валюту из голого «руб.» не берёт."""
    if not text:
        return ""
    m = re.search(r"(\d[\d\s\xa0]*)(?:[.,](\d{1,2}))?\s*руб(?:\.|л)?\w*(?:\s*(\d{1,2})\s*коп)?", text)
    if not m:
        p = A.parse_price(text)
        return f"{p} BYN" if p and "BYN" not in p else p
    rub = re.sub(r"[\s\xa0]", "", m.group(1))
    kop = m.group(2) or m.group(3) or ""
    val = f"{rub}.{kop}".rstrip(".").replace(".00", "")
    return f"{val} BYN"


def _phones(text: str) -> str:
    return ", ".join(p.strip(" ,") for p in PHONE_RX.findall(text or ""))[:100]


def _area(text: str) -> float | str:
    m = re.search(r"(\d[\d\s]*(?:[.,]\d+)?)\s*(?:кв\.?\s*м|м\.?\s*кв|м²)", text or "")
    if not m:
        return ""
    try:
        return float(m.group(1).replace(" ", "").replace(",", "."))
    except ValueError:
        return ""


# ── Гомель (bitrix) ──────────────────────────────────────────────────────────

def _gomel_detail(url: str) -> dict | None:
    soup = BeautifulSoup(A.fetch(url), "lxml")
    h1 = soup.find("h1")
    if not h1:
        return None
    rows = {}
    for tr in soup.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) == 2:
            rows[tds[0].get_text(" ", strip=True).rstrip(":")] = tds[1].get_text(" ", strip=True)
    holder = rows.get("Балансодержатель и его контакты", "")
    desc = ". ".join(filter(None, [rows.get("Полная информация об объекте", ""),
                                   rows.get("Условия продажи", "")]))[:500]
    way = rows.get("Способ вовлечения", "")
    # фото объекта: <a> на полноразмер внутри .gallery (голые img /upload/iblock/ — логотипы шапки)
    pics = [urllib.parse.urljoin(GOMEL_BASE, a["href"])
            for a in soup.select(".gallery a[href*='/upload/']")][:3]
    nu = A.norm_url(url)
    obj = rows.get("Наименование объекта") or h1.get_text(strip=True)
    return {
        "Тип торгов": f"Продажа за 1 БВ ({way})" if way else "Продажа за 1 БВ",
        "Объект": obj,
        "Адрес": rows.get("Адрес объекта", ""),
        "Район / Город": (rows.get("Адрес объекта", "").split(",") + [""])[0].strip(),
        "Площадь, м²": _area(rows.get("Площадь объекта", "")),
        "Начальная цена": _price_byn(rows.get("Цена лота") or rows.get("Недвижимости", "")),
        "Задаток": _price_byn(rows.get("Задаток", "")),
        "Организатор": holder.split("тел")[0].strip(" ,.") or GOMEL_ORG_FALLBACK,
        "Телефон": _phones(holder),
        "Ссылка": nu,
        "Источник": "gomeloblim.gov.by",
        "Фото URL": ", ".join(pics),
        "Описание": desc,
        "Хэш": A.make_hash(nu, obj),
    }


def collect_gomel(limit: int = 0) -> list[dict]:
    seen, items = set(), []
    for page in range(1, 31):
        url = f"{GOMEL_BASE}/realty/?price_base=Y&PAGEN_1={page}"
        html = A.fetch(url)
        if "Ничего не найдено" in html:
            break
        # bitrix прокидывает в href весь query (в т.ч. &PAGEN_1=…) — матчим нестрого
        ids = re.findall(r'href="/realty/(\d+)/\?[^"]*price_base=Y', html)
        new = [i for i in dict.fromkeys(ids) if i not in seen]
        if not new:
            break
        for oid in new:
            seen.add(oid)
            try:
                it = _gomel_detail(f"{GOMEL_BASE}/realty/{oid}/")
            except Exception as e:  # noqa: BLE001
                print(f"  ⛔ gomel {oid}: {type(e).__name__}: {e}")
                continue
            if it:
                items.append(it)
                print(f"  ✓ gomel {oid}: {it['Объект'][:60]} | {it['Начальная цена']}")
            if limit and len(items) >= limit:
                return items
            time.sleep(PAUSE)
    return items


# ── Минобл (Joomla K2) ───────────────────────────────────────────────────────

def _minobl_detail(url: str) -> dict | None:
    soup = BeautifulSoup(A.fetch(url), "lxml")
    h1 = soup.find("h1")
    fields = {}
    for tr in soup.select(".auction-single--tr"):
        tds = tr.select(".auction-single--td")
        if len(tds) == 2:
            k = tds[0].get_text(" ", strip=True).rstrip(":")
            if k not in fields:  # «Дата проведения» встречается дважды — первое с временем
                fields[k] = tds[1].get_text(" ", strip=True)
    obj = h1.get_text(strip=True) if h1 else fields.get("Название*", "")
    if not obj:
        return None
    # описание: текст после метки «Описание:» в теле карточки
    m = re.search(r"Описание:\s*(.{20,600}?)\s*Дата проведения:",
                  soup.get_text(" ", strip=True))
    date_iso = ""
    dm = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", fields.get("Дата проведения", ""))
    if dm:
        date_iso = f"{dm.group(3)}-{dm.group(2)}-{dm.group(1)}"
    raw_price = fields.get("Начальная цена", "")
    if re.search(r"(?i)базов\w*\s*величин", raw_price):  # цена словами «Одна базовая величина»
        price, is_1bv = "45 BYN (1 базовая величина)", True
    else:
        price = _price_byn(raw_price)
        # 1 БВ в 2026 = 45 руб: двузначная цена = символическая продажа
        is_1bv = bool(re.match(r"^\d{1,2}(\.\d+)? BYN$", price))
    kind = "Продажа за 1 БВ (аукцион)" if is_1bv else "Аукцион (госимущество)"
    pics = [urllib.parse.urljoin(MINOBL_BASE, s) for s in
            dict.fromkeys(re.findall(r'(/media/k2/items/cache/[a-f0-9]+_[LX]+\.jpg)', str(soup)))][:3]
    nu = A.norm_url(url)
    return {
        "Тип торгов": kind,
        "Объект": obj,
        "Адрес": fields.get("Место нахождения", ""),
        "Район / Город": fields.get("Регион", ""),
        "Площадь, м²": _area(fields.get("Площадь", "")),
        "Начальная цена": price,
        "Задаток": "",
        "Дата аукциона": date_iso,
        "Организатор": MINOBL_ORG,
        "Телефон": MINOBL_PHONE,
        "Ссылка": nu,
        "Источник": "minoblim.by",
        "Фото URL": ", ".join(pics),
        "Описание": (m.group(1).strip() if m else "")[:500],
        "Хэш": A.make_hash(nu, obj),
    }


def collect_minobl(limit: int = 0) -> list[dict]:
    seen, items = set(), []
    for start in range(0, 160, 16):
        html = A.fetch(f"{MINOBL_BASE}/ru/auktsiony?start={start}")
        urls = [u for u in dict.fromkeys(
            re.findall(r"parent\.location='(/ru/auktsiony/item/[^']+)'", html)) if u not in seen]
        if not urls:
            break
        for u in urls:
            seen.add(u)
            try:
                it = _minobl_detail(urllib.parse.urljoin(MINOBL_BASE, u))
            except Exception as e:  # noqa: BLE001
                print(f"  ⛔ minobl {u[-40:]}: {type(e).__name__}: {e}")
                continue
            if it:
                items.append(it)
                print(f"  ✓ minobl: {it['Объект'][:60]} | {it['Начальная цена']} | {it['Дата аукциона']}")
            if limit and len(items) >= limit:
                return items
            time.sleep(PAUSE)
    return items


def main():
    limit = 0
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    prev = A.load_prev(OUT)
    prev_hashes = {str(r.get("Хэш")) for r in prev.values() if r.get("Хэш")} if prev else set()
    items = []
    print("== Гомель: объекты за 1 БВ ==")
    items += collect_gomel(limit)
    print("== Минобл: аукционы госимущества ==")
    items += collect_minobl(limit)
    A.write_excel(items, OUT, prev_hashes=prev_hashes)
    print(f"Итого {len(items)} лотов → {OUT.name}")


if __name__ == "__main__":
    main()

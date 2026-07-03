"""tcbank_bank — аукционы недвижимости ЗАО «ТК Банк» (tcbank.by/about/selling/).

Серверный HTML: аукцион = <table> с ячейкой «Начальная цена», строки «метка | значение»,
лоты внутри таблицы отделены <td colspan> «Лот N» (вордовская HTML-паста).
Парс-ядро parse_tcbank написал Groq через петлю делегатов (судья на живой фикстуре),
дочинил Claude: хвостовая точка предложения ломала float цены; лоты-фантомы из служебных
строк; nbsp в телефоне. Телефон в лоте — продавца (для обзвона ценнее организатора).
Лотов немного (~2), но крупные (ТЦ 4339 м², 8.3 млн BYN).

Запуск: ./bin/python tcbank_bank.py  → banks_tcbank.xlsx
"""
import re
from pathlib import Path

from bs4 import BeautifulSoup

import auctions_common as A

LIST_URL = "https://www.tcbank.by/about/selling/"


# --- ядро от Groq (петля делегатов 03.07.2026) + фиксы Claude ---
def parse_tcbank(html):
    """Аукционы банка tcbank.by из HTML страницы. Возвращает list[dict]."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for table in soup.find_all("table"):
        if not table.find(string=lambda s: s and "Начальная цена" in s):
            continue
        common_date = ""
        common_phone = ""
        current = None
        rows = table.find_all("tr")
        for tr in rows:
            tds = tr.find_all("td")
            if not tds:
                continue
            # начало нового лота
            if len(tds) == 1 and tds[0].has_attr("colspan"):
                if current and (current["title"] or current["price"]):
                    items.append(current)
                current = {
                    "title": "",
                    "address": "",
                    "area": None,
                    "price": None,
                    "deposit": "",
                    "date": common_date,
                    "phone": common_phone,
                }
                continue
            if len(tds) != 2:
                continue
            label = tds[0].get_text(strip=True)
            value_td = tds[1]
            value_text = value_td.get_text(separator=" ", strip=True)

            # общие данные таблицы
            if label.startswith("Дата, время и место проведения аукциона"):
                common_date = value_text[:10] if len(value_text) >= 10 else ""
                if current:
                    current["date"] = common_date
                continue
            if any(w in label.lower() for w in ("телефон", "организатор", "продавц")):
                m = re.search(r"375[\d\s\xa0()\-]{7,}", value_text)
                common_phone = m.group(0).strip() if m else ""
                if current:
                    current["phone"] = common_phone
                continue

            # если лот ещё не создан (таблица без "Лот N")
            if not current:
                current = {
                    "title": "",
                    "address": "",
                    "area": None,
                    "price": None,
                    "deposit": "",
                    "date": common_date,
                    "phone": common_phone,
                }

            # данные лота
            if label.startswith("Сведения о предмете"):
                full = value_td.get_text(separator=" ", strip=True)
                current["title"] = full[:120]

                address = ""
                for b in value_td.find_all("b"):
                    txt = b.get_text(strip=True)
                    if any(sub in txt for sub in ("обл", "р-н", "г.", "ул.")):
                        address = re.sub(r",?\s*площадью.*$", "", txt).strip()
                        break
                current["address"] = address

                area_match = re.search(r"([\d.,]+)\s*кв\.?м", value_text, re.IGNORECASE)
                if area_match:
                    num = area_match.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")
                    try:
                        current["area"] = float(num)
                    except Exception:
                        current["area"] = None
                continue

            if "Начальная цена предмета" in label:
                # число с разделителями ’ ' пробел/nbsp; запятая = десятичная (fix Claude:
                # хвостовая точка предложения ломала float)
                m = re.search(r"\d[\d\s\xa0’']*(?:,\d{1,2})?", value_text)
                if m:
                    num = re.sub(r"[\s\xa0’']", "", m.group(0)).replace(",", ".")
                    try:
                        current["price"] = float(num)
                    except ValueError:
                        current["price"] = None
                continue

            if label.startswith("Размер задатка"):
                current["deposit"] = value_text[:200]
                continue

        if current and (current["title"] or current["price"]):
            items.append(current)
    return items
# --- конец ядра ---


def collect() -> list:
    html = A.fetch(LIST_URL)
    if not html:
        print("  ⚠ страница не получена")
        return []
    items = []
    for lot in parse_tcbank(html):
        it = A.blank_item("tcbank.by")
        it["Тип торгов"] = "Аукцион банка"
        it["Объект"] = re.sub(r"\s+", " ", lot["title"]).strip()[:200]
        it["Адрес"] = re.sub(r"\s+", " ", lot["address"]).strip()
        it["Площадь, м²"] = str(lot["area"]) if lot["area"] else ""
        it["Начальная цена"] = f"{lot['price']:.0f} BYN" if lot["price"] else ""
        it["Задаток"] = lot["deposit"]
        it["Дата аукциона"] = lot["date"]
        it["Телефон"] = re.sub(r"\s+", " ", lot["phone"]).strip()
        it["Организатор"] = "ЗАО «ТК Банк»"
        it["Ссылка"] = LIST_URL
        it["Хэш"] = A.make_hash(LIST_URL, it["Объект"], it["Начальная цена"])
        items.append(it)
    return items


def main():
    out = Path("banks_tcbank.xlsx").resolve()
    items = collect()
    print(f"[TCBANK] лотов: {len(items)}")
    if items:
        A.write_excel(items, out, prev_hashes=set())
        for c in ("Объект", "Начальная цена", "Адрес", "Площадь, м²", "Телефон", "Дата аукциона"):
            n = sum(1 for r in items if r.get(c))
            print(f"  {c:16}: {n}/{len(items)}")


if __name__ == "__main__":
    main()

"""zepter_bank — имущество Цептер Банка (zepterbank.by/bank/information/sale/).

⚠ Сайт за JS-антиботом: первый ответ — челлендж-страница, которая ставит куку
`hg-security` и перезагружается. Значение куки лежит ПРЯМО в челлендже → обход
в два запроса (_fetch: получить челлендж → вынуть куку → повторить с Cookie).
Секция «Недвижимость» → collapse-блоки; описание содержит категорию, площадь,
адрес, «Стоимость: N руб» и телефон. Объектов мало (~2), но с ценой и контактом.
parse_zepter написал Claude (GLM в петле не осилил: выдумал импорт, битый regex).

Запуск: ./bin/python zepter_bank.py  → banks_zepter.xlsx
"""
import re
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

import auctions_common as A

LIST_URL = "https://www.zepterbank.by/bank/information/sale/"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def _fetch(url: str) -> str:
    """GET с обходом hg-security-челленджа (кука лежит в самом челлендже)."""
    try:
        req = urllib.request.Request(url, headers=UA)
        html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ fetch: {type(e).__name__}: {e}")
        return ""
    if "hg-security" in html and len(html) < 5000:
        m = re.search(r'(hg-security=[^;"]+)', html)
        if not m:
            return ""
        try:
            req = urllib.request.Request(url, headers=dict(UA, Cookie=m.group(1)))
            html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ fetch с кукой: {type(e).__name__}: {e}")
            return ""
    return html


def parse_zepter(html):
    """Секция «Недвижимость»: li.prprt_list_item → title + описание collapse-тела."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for sect in soup.find_all("div", class_="sectblock"):
        h3 = sect.find("h3", class_="prprt_title")
        if not h3 or "Недвижимость" not in h3.get_text():
            continue
        for li in sect.find_all("li", class_="prprt_list_item"):
            span = li.find("span", class_="undecor")
            body = li.find("div", class_="row_body")
            if not span or not body:
                continue
            desc = re.sub(r"\s+", " ", body.get_text(" ", strip=True))[:1500]
            mcat = re.search(r"Категория\s*[-–]\s*([^.]{3,80}?)(?:\s{2,}|Капитальн|Незаверш|$)", desc)
            marea = re.search(r"площад\w*\s*[:–-]?\s*([\d\s\xa0]+[.,]?\d*)\s*кв\.?\s*м", desc, re.I)
            area = None
            if marea:
                try:
                    area = float(marea.group(1).replace(" ", "").replace("\xa0", "").replace(",", "."))
                except ValueError:
                    pass
            mprice = re.search(r"(?:Стоимость|цена)\s*:?\s*([\d\s\xa0]+(?:,\d{1,2})?)", desc, re.I)
            price = None
            if mprice:
                try:
                    price = float(mprice.group(1).replace(" ", "").replace("\xa0", "").replace(",", "."))
                except ValueError:
                    pass
            items.append({
                "title": span.get_text(strip=True),
                "category": (mcat.group(1).strip() if mcat else ""),
                "area": area,
                "description": desc,
                "price": price,
            })
    return items


def collect() -> list:
    html = _fetch(LIST_URL)
    if not html:
        print("  ⚠ страница не получена")
        return []
    items = []
    for obj in parse_zepter(html):
        it = A.blank_item("zepterbank.by")
        it["Тип торгов"] = "Продажа банком"
        it["Объект"] = obj["title"][:200]
        it["Описание"] = obj["description"]
        madr = re.search(r"[Аа]дрес\w*\s*:?\s*([^.]{5,120})", obj["description"])
        it["Адрес"] = madr.group(1).strip() if madr else A.extract_re_address(obj["description"], obj["title"])
        it["Площадь, м²"] = str(obj["area"]) if obj["area"] else ""
        it["Начальная цена"] = f"{obj['price']:.2f} BYN" if obj["price"] else ""
        mph = re.search(r"\+?375[\d\s\xa0()\-]{7,17}", obj["description"])
        it["Телефон"] = re.sub(r"\s+", " ", mph.group(0)).strip() if mph else ""
        it["Организатор"] = 'ЗАО «Цептер Банк»'
        it["Ссылка"] = LIST_URL
        it["Хэш"] = A.make_hash(LIST_URL, it["Объект"])
        items.append(it)
    return items


def main():
    out = Path("banks_zepter.xlsx").resolve()
    items = collect()
    print(f"[ZEPTER] объектов: {len(items)}")
    if items:
        A.write_excel(items, out, prev_hashes=set())
        for c in ("Объект", "Начальная цена", "Адрес", "Площадь, м²", "Телефон"):
            n = sum(1 for r in items if r.get(c))
            print(f"  {c:16}: {n}/{len(items)}")


if __name__ == "__main__":
    main()

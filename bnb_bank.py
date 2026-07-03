"""bnb_bank — реализуемое имущество БНБ-Банка (o-nas/nashe-delo/realizuemoe-imushchestvo).

⚠ ГЕО-БЛОК (под VPN даже главная в таймауте). Живой сбор — `bank_geo_collect.py` БЕЗ VPN;
--fixtures берёт страницу последнего зонда bank_geo_out2/. Объектов мало (~2), но крупные
(ресторан 3904 м² Могилёв, торговые помещения Брест). Аккордеоны: <a class="accordion__head">
(заголовок = название + адрес) + <div class="accordion__body"> (описание, таблица
характеристик, галерея). Ядро parse_bnb — Claude (GLM в петле не совладал с аккордеонами).

Запуск: ./bin/python bnb_bank.py [--fixtures]  → banks_bnb.xlsx
"""
import argparse
import re
import socket
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

import auctions_common as A

BASE = "https://bnb.by"
LIST_URL = BASE + "/o-nas/nashe-delo/realizuemoe-imushchestvo/"
FIXTURE = Path(__file__).parent / "bank_geo_out2/bnb/o-nas_nashe-delo_realizuemoe-imushchestvo.html"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


# --- ядро (Claude, судья на живой фикстуре) ---
def parse_bnb(html):
    """Реализуемое имущество bnb.by: аккордеоны «заголовок + тело с таблицей и галереей»."""
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    items = []
    heads = soup.find_all(class_="accordion__head")  # это <a>, тег не фиксируем
    bodies = soup.find_all("div", class_="accordion__body")
    for head, body in zip(heads, bodies):
        title = re.sub(r"\s+", " ", head.get_text(" ", strip=True)).strip()
        if not title:
            continue
        fields = {}
        table = body.find("table")
        if table:
            for tr in table.find_all("tr"):
                tds = tr.find_all("td")
                if len(tds) == 2:
                    k = re.sub(r"\s+", " ", tds[0].get_text(" ", strip=True))
                    v = re.sub(r"\s+", " ", tds[1].get_text(" ", strip=True))
                    fields[k] = v
        area = None
        for k, v in fields.items():
            if "Площадь" in k:
                m = re.search(r"[\d\s\xa0]+(?:[.,]\d+)?", v)
                if m:
                    try:
                        area = float(m.group(0).replace(" ", "").replace("\xa0", "").replace(",", "."))
                    except ValueError:
                        pass
                break
        # описание: текст тела до таблицы
        desc_parts = []
        for el in body.descendants:
            if el is table:
                break
            if isinstance(el, str):
                desc_parts.append(el)
        desc = re.sub(r"\s+", " ", "".join(desc_parts)).strip()[:800]
        photos = []
        for a in body.find_all("a", class_="about-gallery_img", href=True):
            if a["href"] not in photos:
                photos.append(a["href"])
            if len(photos) >= 3:
                break
        items.append({
            "title": title,
            "address": fields.get("Адрес", ""),
            "area": area,
            "purpose": fields.get("Назначение", ""),
            "year": fields.get("Год постройки", ""),
            "description": desc,
            "photos": photos,
        })
    return items
# --- конец ядра ---


def get_html(use_fixtures: bool) -> str:
    if not use_fixtures:
        socket.setdefaulttimeout(20)
        try:
            req = urllib.request.Request(LIST_URL, headers=UA)
            return urllib.request.urlopen(req).read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ живой сайт недоступен ({type(e).__name__}) — гео-блок? Запусти без VPN "
                  f"или с --fixtures")
            return ""
    if FIXTURE.exists():
        print(f"  (данные из фикстуры зонда: {FIXTURE.name})")
        return FIXTURE.read_text(encoding="utf-8")
    print("  ⚠ фикстуры нет — сначала прогнать bank_geo_probe2.py без VPN")
    return ""


def collect(use_fixtures: bool) -> list:
    html = get_html(use_fixtures)
    items = []
    for obj in parse_bnb(html):
        it = A.blank_item("bnb.by")
        it["Тип торгов"] = "Продажа банком"
        it["Объект"] = obj["title"][:200]
        it["Адрес"] = obj["address"] or obj["title"].split(",", 1)[-1].strip()
        it["Площадь, м²"] = str(obj["area"]) if obj.get("area") else ""
        extra = [x for x in (obj.get("purpose"), f"Год: {obj['year']}" if obj.get("year") else "") if x]
        it["Описание"] = (". ".join(extra) + ". " if extra else "") + obj["description"]
        it["Организатор"] = "ЗАО «БНБ-Банк»"
        it["Ссылка"] = LIST_URL
        it["Фото URL"] = BASE + obj["photos"][0] if obj.get("photos") else ""
        it["Хэш"] = A.make_hash(LIST_URL, it["Объект"])
        items.append(it)
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", action="store_true", help="взять HTML из bank_geo_out2 (без сети)")
    cfg = ap.parse_args()
    out = Path("banks_bnb.xlsx").resolve()
    items = collect(cfg.fixtures)
    print(f"[BNB] объектов: {len(items)}")
    if items:
        A.write_excel(items, out, prev_hashes=set())
        for c in ("Объект", "Адрес", "Площадь, м²", "Фото URL"):
            n = sum(1 for r in items if r.get(c))
            print(f"  {c:16}: {n}/{len(items)}")


if __name__ == "__main__":
    main()

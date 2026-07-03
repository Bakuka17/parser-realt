"""belapb_bank — имущество Белагропромбанка (bitrix-каталог, серверный HTML, ~33 карточки).

Два раздела: залоговое имущество клиентов банка + имущество самого банка.
Парс-ядро parse_belapb написано GLM через петлю делегатов (delegate_loop, судья на живой
фикстуре 33/33), обёртка/схема/QA — Claude. «Тип торгов» = «Продажа банком» (как belinvest).
Карточки без ссылки на деталь — всё берём из листинга; цена/адрес/телефон достаются
из текста карточки (есть не у всех: часть карточек = «изучение спроса» без цены).

Запуск: ./bin/python belapb_bank.py  → banks_belapb.xlsx
"""
import re
from pathlib import Path

from bs4 import BeautifulSoup

import auctions_common as A

BASE = "https://www.belapb.by"
URLS = [
    BASE + "/about/catalog/zalozhennoe-i-inoe-imushchestvo-klientov-banka/",
    BASE + "/about/catalog/imushchestvo-banka/",
]


# --- ядро от GLM (петля делегатов 03.07.2026, зелёный судья со 2-й итерации) ---
def parse_belapb(html):
    if not html:
        return []
    soup = BeautifulSoup(html, 'html.parser')
    cards = soup.find_all('div', class_='prop-sale__card')
    items = []
    for card in cards:
        content = card.find('div', class_='prop-sale__card-content')
        if not content:
            continue
        zag = content.find('div', class_='zag')
        if not zag:
            continue
        title = zag.get_text(strip=True)
        if not title:
            continue
        list_info = content.find('ul', class_='list-info')
        kind = ""
        method = ""
        if list_info:
            for li in list_info.find_all('li'):
                spans = li.find_all('span')
                if len(spans) >= 2:
                    label = spans[0].get_text(strip=True)
                    value = spans[1].get_text(strip=True)
                    if label == "Вид имущества:":
                        kind = value
                    elif label == "Способ реализации:":
                        method = value
        card_text_div = card.find('div', class_='prop-sale__card-text')
        text = card_text_div.get_text(strip=True)[:1200] if card_text_div else ""
        photos = []
        photo_links = card.find_all('a', class_='item', href=True)
        seen_photos = set()
        for link in photo_links:
            href = link['href']
            if href not in seen_photos:
                photos.append(href)
                seen_photos.add(href)
                if len(photos) >= 3:
                    break
        item = {
            "title": title,
            "kind": kind,
            "method": method,
            "text": text,
            "photos": photos
        }
        items.append(item)
    return items
# --- конец ядра GLM ---


def collect() -> list:
    items = []
    for url in URLS:
        html = A.fetch(url)
        if not html:
            print(f"  ⚠ не получен: {url}")
            continue
        for c in parse_belapb(html):
            # только недвижимость: «Вид имущества» = Жилая/Нежилая
            # (в залоговом разделе намешаны грузовики/оборудование/акции)
            if "жил" not in (c["kind"] or "").lower():
                continue
            it = A.blank_item("belapb.by")
            it["Тип торгов"] = "Продажа банком"
            it["Объект"] = c["title"][:200]
            desc = c["text"]
            it["Описание"] = (f"Способ: {c['method']}. " if c["method"] else "") + desc
            it["Адрес"] = A.extract_re_address(desc, c["title"])
            ar = A.extract_area(desc)
            it["Площадь, м²"] = str(ar) if ar else ""
            m = re.search(r"(?i)стоимость[^\d]{0,60}([\d\s\xa0’']{3,}(?:[.,]\d{1,2})?)", desc)
            it["Начальная цена"] = A.parse_price(m.group(1) + " бел. руб.") if m else ""
            mph = re.search(r"\+?375[\s\d()\-]{7,17}", desc)
            it["Телефон"] = mph.group(0).strip() if mph else ""
            it["Организатор"] = 'ОАО "Белагропромбанк"'
            it["Ссылка"] = url
            it["Фото URL"] = BASE + c["photos"][0] if c["photos"] else ""
            it["Хэш"] = A.make_hash(url, it["Объект"])
            items.append(it)
    return items


def main():
    out = Path("banks_belapb.xlsx").resolve()
    items = collect()
    print(f"[BELAPB] объектов: {len(items)}")
    if items:
        A.write_excel(items, out, prev_hashes=set())
        for c in ("Объект", "Начальная цена", "Адрес", "Площадь, м²", "Телефон", "Фото URL"):
            n = sum(1 for r in items if r.get(c))
            print(f"  {c:16}: {n}/{len(items)} ({100 * n // len(items)}%)")


if __name__ == "__main__":
    main()

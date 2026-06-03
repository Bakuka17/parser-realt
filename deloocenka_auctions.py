"""deloocenka_auctions — парсер аукционов ООО «Деловая оценка» (deloocenka.by/aukzioni).

Серверный HTML (Bootstrap). Одна страница /aukzioni с тремя вкладками:
  • #menu1 — назначенные / планируемые аукционы,
  • #menu2 — предлагается к продаже,
  • #menu3 — проданное имущество (НЕ берём — для обзвона бесполезно).
Каждый лот — <div class="col-xl-9"> внутри секции:
  <h2>Тип (продажа/аренда) - Адрес</h2>, <p>Продавец: ..</p>,
  опц. <p>Дата и время аукциона: DD.MM.YYYYг. ..</p>,
  <p>Цена: ../Начальная цена (с НДС): ..</p>, <a class="btn">Подробнее</a> → деталь.
Деталь (/aukzionXX) серверная: площадь, цена, задаток, телефоны, полный адрес, описание.

Берём ТОЛЬКО недвижимость (позитивный фильтр по типу из заголовка — площадка смешанная:
есть авто, оборудование, станки) и только активные вкладки (#menu1 + #menu2).
Парсинг — BeautifulSoup, поля — через хелперы auctions_common.

Запуск:  ./bin/python deloocenka_auctions.py
"""
from __future__ import annotations

import re
import time
import random
from pathlib import Path

from bs4 import BeautifulSoup

import auctions_common as A

SOURCE = "deloocenka.by"
BASE = "http://deloocenka.by"
LIST_URL = "http://deloocenka.by/aukzioni"
ACTIVE_TABS = ["menu1", "menu2"]  # планируемые + предлагается; menu3 (проданное) пропускаем

# Телефоны организатора (шапка сайта) — фолбэк, если на деталке номера не нашлись.
ORG_PHONES = "+375 44 750-40-03, +375 29 303-30-62"

# Позитивный детектор недвижимости по заголовку лота (площадка смешанная).
RE_TYPE = re.compile(
    r"квартир|помещени|здани|недвиж|кафе|ресторан|столов|магазин|павильон|торгов\w*\s+объект|"
    r"\bдом\b|коттедж|дач|земельн|\bземл|участ(?:ок|ка)|склад|офис|администрат|"
    r"строени|сооружени|гараж|\bбаза\b|комплекс\s+(?:имуществ|недвиж|зданий)|общепит|производствен\w*\s+и\s+складск",
    re.I,
)


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def _p_value(block, label_re: str) -> str:
    """Текст <p>, начинающегося с метки (напр. 'Продавец:', 'Цена:'), без самой метки."""
    for p in block.find_all("p"):
        t = A.clean(p.get_text(" ", strip=True))
        m = re.match(label_re, t, re.I)
        if m:
            return t[m.end():].strip(" :-")
    return ""


def parse_listing(html: str) -> list[dict]:
    """Со страницы /aukzioni собирает карточки недвижимости из активных вкладок.
    Возвращает [{url, title, seller, date_raw, price_raw, photo}]."""
    soup = soup_of(html)
    cards: list[dict] = []
    seen: set[str] = set()
    for tab in ACTIVE_TABS:
        sec = soup.find(id=tab)
        if not sec:
            continue
        for block in sec.select("div.col-xl-9"):
            h2 = block.find(["h2", "h3"])
            if not h2:
                continue
            title = A.clean(h2.get_text(" ", strip=True))
            # тип лота — часть ДО «(продажа)» и до « - адрес» (чтобы фильтр не цеплял
            # «дом»/«переулок» из адреса у не-недвижимости вроде «Доля в уставном фонде … дом 5»)
            head = re.split(r"\(|\s[-–]\s", title, maxsplit=1)[0]
            if not title or not RE_TYPE.search(head):
                continue  # не недвижимость — пропускаем
            link = block.find("a", string=re.compile("Подробнее")) or block.find("a", href=True)
            href = link["href"].strip() if link and link.get("href") else ""
            if not href:
                continue
            url = href if href.startswith("http") else BASE + "/" + href.lstrip("/")
            nu = A.norm_url(url)
            if nu in seen:
                continue
            seen.add(nu)
            # фото из соседней колонки (row → col-xl-3 img)
            photo = ""
            row = block.parent
            if row:
                img = row.find("img", src=True)
                if img:
                    src = img["src"].strip()
                    photo = src if src.startswith("http") else BASE + "/" + src.lstrip("/")
            cards.append({
                "url": url,
                "title": title,
                "seller": _p_value(block, r"продав\w*"),
                "date_raw": _p_value(block, r"дата[^:]*"),
                "price_raw": _p_value(block, r"(?:начальн\w*\s+)?цен\w*"),
                "photo": photo,
                "tab": tab,
            })
    return cards


def detail_text(soup: BeautifulSoup) -> str:
    for t in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        t.decompose()
    return A.clean(soup.get_text(" ", strip=True))


def extract_description(soup: BeautifulSoup) -> str:
    """Описание объекта из контент-таблицы детали (вёрстка из Word — table.MsoNormalTable).
    Временная чистка контактов/болванки; надёжный чистильщик — clean_auction_description
    (делегируется DeepSeek, drop-in замена)."""
    tbl = soup.find("table", class_="MsoNormalTable")
    if not tbl:
        return ""  # нет контент-таблицы — лучше пусто, чем промо-болванка сайта
    # извлечение (моё) + чистка контактов/болванки общим хелпером (каркас DeepSeek)
    return A.clean_auction_description(A.clean(tbl.get_text(" ", strip=True)))


def parse_detail(card: dict, html: str) -> dict:
    soup = soup_of(html)
    text = detail_text(soup)
    nu = A.norm_url(card["url"])

    it = A.blank_item(SOURCE)
    it["Тип торгов"] = "Аукцион"
    it["Объект"] = card["title"]
    it["Ссылка"] = nu

    # адрес: из заголовка (после « - »), иначе из текста деталки
    addr = ""
    if " - " in card["title"]:
        tail = card["title"].split(" - ", 1)[1]
        addr = A.extract_address(tail) or tail.strip()
    if not addr:
        addr = A.extract_address(text) or ""
    it["Адрес"] = addr
    mcity = re.search(r"г\.\s*([А-ЯЁ][а-яё-]+)", addr or card["title"])
    if mcity:
        it["Район / Город"] = "г. " + mcity.group(1)

    # площадь — из деталки (короткий приоритет — заголовок)
    area = A.extract_area(card["title"]) or A.extract_area(text)
    it["Площадь, м²"] = str(area) if area else ""

    # цена: деталь (прицельно «начальная цена») → лист → любая цена деталки
    price = A.extract_start_price(text) or A.parse_price(card.get("price_raw", ""))
    if not price:
        # .{0,45}? (а не [^\d]) — чтобы перешагнуть «(5%) с учётом НДС:» перед суммой
        m = re.search(r"цен\w*.{0,45}?(\d[\d ]*[.,]?\d*)\s*(?:бел\.?\s*руб|BYN|руб|Br)", text, re.I)
        if m:
            price = A.parse_price(m.group(0))
    it["Начальная цена"] = price

    # задаток: «Задаток (5%) с учётом НДС: 163 414,40 бел.руб» — пускаем цифры в зазоре
    mz = re.search(r"задат\w*.{0,45}?(\d[\d ]*[.,]?\d*)\s*(?:бел\.?\s*руб|BYN|руб|Br)", text, re.I)
    if mz:
        it["Задаток"] = A.parse_price(mz.group(0))

    # дата — только реальная дата аукциона из листинга; «не назначены (повторные торги)»
    # или отсутствие → пусто (НЕ берём случайную дату с деталки, она вводит в заблуждение)
    it["Дата аукциона"] = A.parse_date(card.get("date_raw", ""))

    # организатор: продавец (владелец имущества — самый полезный контакт)
    it["Организатор"] = card.get("seller", "") or "ООО «Деловая оценка»"

    # телефоны: деталь → фолбэк номера организатора
    it["Телефон"] = A.extract_phones(html) or ORG_PHONES

    if card.get("photo"):
        it["Фото URL"] = card["photo"]

    it["Описание"] = extract_description(soup)

    it["Хэш"] = A.make_hash(nu, it["Объект"])
    return it


def parse_deloocenka() -> list[dict]:
    print(f"🔨 deloocenka_auctions | источник: {SOURCE}")
    html = A.fetch(LIST_URL)
    if not html:
        print("  ✖ не загрузил список"); return []
    cards = parse_listing(html)
    print(f"  карточек недвижимости (активные вкладки): {len(cards)}")
    items: list[dict] = []
    for i, card in enumerate(cards, 1):
        dhtml = A.fetch(card["url"])
        if not dhtml:
            continue
        it = parse_detail(card, dhtml)
        items.append(it)
        print(f"  [{i}/{len(cards)}] + {it['Дата аукциона'] or '????'} | "
              f"{it['Объект'][:45]} | {it['Начальная цена'] or '—'}")
        time.sleep(random.uniform(1.0, 2.0))
    return items


if __name__ == "__main__":
    res = parse_deloocenka()
    print(f"\n[DELOOCENKA] лотов недвижимости: {len(res)}")
    if res:
        for c in A.AUCTION_COLUMNS:
            n = sum(1 for r in res if r.get(c))
            print(f"  {c:18}: {n}/{len(res)} ({100 * n // len(res)}%)")
    A.write_excel(res, Path("auctions_deloocenka.xlsx"))

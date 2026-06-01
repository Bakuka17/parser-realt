"""eauction_auctions — парсер аукционов площадки e-auction.by, раздел недвижимости.

Сайт на Bitrix, серверный HTML (контент в исходнике). Список лотов:
https://e-auction.by/commerce/ — карточки `<a class="product-item" href="/{раздел}/{slug}/">`
(тот же шаблон catalog.section, что и в блоке «Популярные в разделе» на деталке).
Внутри карточки: `.product_art` (№ лота), `.text-header` (заголовок), `.bx_price` (цена).

Деталь (компонент auction_view_rev4):
  • <h1> — заголовок лота (Объект);
  • блоки `.information-layout-item` с `<p class="text-header"><b>Начальная цена имущества:</b></p>`
    → «Начальная цена», «Сумма задатка:» → «Задаток», «Время начала торгов:» → дата;
  • «Аукцион № <span>...</span>» — номер;
  • таблица `.product-specs__table`: строка «Местоположение имущества» → адрес,
    «Контакты организатора аукциона»/«Контакты:» → телефоны,
    блок «Организатор торгов» → «Наименование» организатора.

Извлечение полей опирается на A.* (clean/extract_*), плюс точечные выборки BeautifulSoup.

Запуск:  ./bin/python eauction_auctions.py
"""
from __future__ import annotations

import re
import time
import random
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

import auctions_common as A

SOURCE = "e-auction.by"
BASE = "https://e-auction.by"
LIST_URL = "https://e-auction.by/commerce/"
OUT = Path("auctions_eauction.xlsx")
MAX_PAGES = 50  # предохранитель от бесконечной пагинации


# ── СПИСОК ───────────────────────────────────────────────────────────────────
def parse_list(html: str) -> list[dict]:
    """Карточки лотов со страницы списка → [{url, title, lot_no, price_raw}]."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    for a in soup.select("a.product-item[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = urljoin(BASE, href)
        # заголовок лота
        th = a.select_one(".product-info .text-header") or a.select_one(".text-header")
        title = A.clean(th.get_text()) if th else (a.get("title") or "")
        if not title:
            # из alt картинки как фолбэк
            img = a.select_one("img[alt]")
            title = (img.get("alt") or "").strip() if img else ""
        art = a.select_one(".product_art")
        lot_no = A.clean(art.get_text()) if art else ""
        pr = a.select_one(".bx_price")
        price_raw = A.clean(pr.get_text()) if pr else ""
        out.append({
            "url": url,
            "title": title.strip(),
            "lot_no": lot_no,
            "price_raw": price_raw,
        })
    return out


def find_next_page(html: str, current: int) -> str | None:
    """Ссылка на следующую страницу пагинации Bitrix (?PAGEN_1=N). None — если нет."""
    soup = BeautifulSoup(html, "lxml")
    # Bitrix-навигация: блок .modern-page-navigation / .navigation, ссылки PAGEN_
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        m = re.search(r"PAGEN_\d+=(\d+)", href)
        if m and int(m.group(1)) == current + 1:
            return urljoin(BASE, href)
    return None


def collect_list_pages() -> list[dict]:
    """Обходит все страницы списка, собирает уникальные карточки (дедуп по norm_url)."""
    cards: list[dict] = []
    seen: set[str] = set()
    page = 1
    url = LIST_URL
    while url and page <= MAX_PAGES:
        print(f"→ список, стр.{page}: {url}")
        html = A.fetch(url)
        if not html:
            break
        page_cards = parse_list(html)
        new_on_page = 0
        for c in page_cards:
            nu = A.norm_url(c["url"])
            if nu in seen:
                continue
            seen.add(nu)
            cards.append(c)
            new_on_page += 1
        print(f"  карточек на странице: {len(page_cards)} (новых уникальных: {new_on_page})")
        if new_on_page == 0:
            break  # страница без новых лотов — конец
        nxt = find_next_page(html, page)
        if not nxt:
            break
        url = nxt
        page += 1
    return cards


# ── ДЕТАЛЬ ───────────────────────────────────────────────────────────────────
def _layout_value(soup: BeautifulSoup, label: str) -> str:
    """Значение из блока `.information-layout-item`, где text-header содержит label.
    Структура: <div class="information-layout-item"><p class="text-header"><b>LABEL</b></p><p>VALUE</p></div>."""
    for item in soup.select(".information-layout-item"):
        hdr = item.select_one(".text-header")
        if not hdr:
            continue
        if label.lower() in A.clean(hdr.get_text()).lower():
            # значение — текст блока без шапки
            ps = item.find_all("p")
            for p in ps:
                if p is hdr or (hdr in p.parents):
                    continue
                val = A.clean(p.get_text())
                if val:
                    return val
            # фолбэк: весь текст блока минус шапка
            full = A.clean(item.get_text())
            return full.replace(A.clean(hdr.get_text()), "").strip()
    return ""


def _spec_value(soup: BeautifulSoup, label: str) -> str:
    """Значение строки таблицы `.product-specs__table` по названию параметра (td-name)."""
    for tr in soup.select(".product-specs__table tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        name = A.clean(tds[0].get_text())
        if label.lower() in name.lower():
            return A.clean(tds[1].get_text())
    return ""


def _organizer(soup: BeautifulSoup) -> str:
    """Организатор торгов: в таблице после заголовка-секции «Организатор торгов» идёт
    строка «Наименование». Берём первую строку «Наименование» после этой секции."""
    in_section = False
    for tr in soup.select(".product-specs__table tr"):
        cls = " ".join(tr.get("class", []))
        if "product-specs__table-title" in cls:
            in_section = "организатор торгов" in A.clean(tr.get_text()).lower()
            continue
        if in_section:
            tds = tr.find_all("td")
            if len(tds) >= 2 and "наименование" in A.clean(tds[0].get_text()).lower():
                return A.clean(tds[1].get_text())
    return ""


def parse_detail(html: str, card: dict) -> dict:
    it = A.blank_item(SOURCE)
    soup = BeautifulSoup(html, "lxml")
    text = A.clean(html)

    # Объект — из <h1>, иначе заголовок карточки
    h1 = soup.find("h1")
    title = A.clean(h1.get_text()) if h1 else ""
    if not title:
        title = card.get("title", "")
    it["Объект"] = title
    it["Тип торгов"] = "Аукцион"

    # Начальная цена: блок макета → прицельный хелпер → цена из карточки
    nstart = _layout_value(soup, "Начальная цена")
    if nstart:
        it["Начальная цена"] = A.parse_price(nstart)
    if not it["Начальная цена"]:
        it["Начальная цена"] = A.extract_start_price(text)
    if not it["Начальная цена"] and card.get("price_raw"):
        it["Начальная цена"] = A.parse_price(card["price_raw"])

    # Задаток
    zal = _layout_value(soup, "задат")
    if zal:
        it["Задаток"] = A.parse_price(zal)

    # Дата аукциона: «Время начала торгов» (фолбэк — окончание приёма заявок / весь текст)
    dt_raw = (_layout_value(soup, "Время начала торгов")
              or _layout_value(soup, "начала торгов")
              or _layout_value(soup, "окончания приёма заявок")
              or _layout_value(soup, "приёма заявок"))
    it["Дата аукциона"] = A.parse_date(dt_raw) or A.parse_date(card.get("price_raw", ""))

    # Организатор
    it["Организатор"] = _organizer(soup)

    # Адрес: «Местоположение имущества» из таблицы, иначе общий хелпер
    loc = _spec_value(soup, "Местоположение")
    if loc:
        it["Адрес"] = loc
        addr_blob = loc
    else:
        addr_blob = ""
        a2 = A.extract_address(title + ". " + text[:2000])
        if a2:
            it["Адрес"] = a2
            addr_blob = a2

    # Район / Город — из адреса
    city_src = it["Адрес"] or title
    mcity = re.search(r"г\.\s*([А-ЯЁ][а-яё-]+)", city_src)
    if mcity:
        it["Район / Город"] = "г. " + mcity.group(1)

    # Площадь — из заголовка/адреса/локации (короткий текст, без мусора полной страницы)
    area = (A.extract_area(title)
            or A.extract_area(loc)
            or A.extract_area(_spec_value(soup, "площад"))
            or A.extract_area(text[:2000]))
    it["Площадь, м²"] = str(area) if area else ""

    # Телефоны
    it["Телефон"] = A.extract_phones(html)

    # Фото URL — первое изображение галереи (если есть)
    img = soup.select_one(".product-preview-image img[src]")
    if img and img.get("src"):
        it["Фото URL"] = urljoin(BASE, img["src"])

    it["Ссылка"] = A.norm_url(card["url"])
    it["Хэш"] = A.make_hash(it["Ссылка"], it["Объект"])
    return it


# ── ОРКЕСТРАЦИЯ ──────────────────────────────────────────────────────────────
def main():
    print(f"🔨 eauction_auctions | источник: {SOURCE} | out: {OUT.name}")
    cards = collect_list_pages()
    print(f"\nвсего уникальных карточек: {len(cards)}")

    items: list[dict] = []
    seen: set[str] = set()
    for i, card in enumerate(cards, 1):
        nu = A.norm_url(card["url"])
        if nu in seen:
            continue
        seen.add(nu)
        dhtml = A.fetch(card["url"])
        if not dhtml:
            continue
        it = parse_detail(dhtml, card)
        if not it["Объект"] or not it["Ссылка"]:
            continue
        items.append(it)
        print(f"  [{i}/{len(cards)}] + {it['Дата аукциона'] or '????'} | "
              f"{it['Объект'][:45]} | {it['Начальная цена'] or '—'}")
        time.sleep(random.uniform(0.6, 1.4))

    print(f"\n📦 Итог: {len(items)} лотов")
    A.write_excel(items, OUT)


if __name__ == "__main__":
    main()

"""konfiskat_auctions — парсер аукционов недвижимости konfiskat.by.

Площадка на Bitrix, серверный HTML. Список:
  https://konfiskat.by/nedvizhimost/auktsiony/filter/clear/apply/
Ссылки лотов вида /nedvizhimost/auktsiony/{N}/ (N — число).
На детальных страницах есть поля «Начальная цена», «Площадь», «Дата».

Парсинг ссылок/заголовков — через BeautifulSoup (НЕ регэкспы по тегам).
Поля (цена/дата/адрес/площадь/телефон) — через хелперы auctions_common.

Запуск:  ./bin/python konfiskat_auctions.py
"""
from __future__ import annotations

import re
import time
import random
from pathlib import Path

from bs4 import BeautifulSoup

import auctions_common as A

SOURCE = "konfiskat.by"
BASE = "https://konfiskat.by"
LIST_URL = "https://konfiskat.by/nedvizhimost/auktsiony/filter/clear/apply/"

# Ссылка лота: /nedvizhimost/auktsiony/12345/  (число, затем слэш и конец)
LOT_HREF_RE = re.compile(r"^(?:https?://konfiskat\.by)?/nedvizhimost/auktsiony/(\d+)/?$")
MAX_PAGES = 100


def soup_of(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def find_lot_links(soup: BeautifulSoup) -> list[str]:
    """Все ссылки лотов /nedvizhimost/auktsiony/N/ со страницы списка (через BS4).
    Возвращает абсолютные URL, без дублей, в порядке появления."""
    out: list[str] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not LOT_HREF_RE.match(href):
            continue
        full = href if href.startswith("http") else BASE + href
        nu = A.norm_url(full)
        if nu in seen:
            continue
        seen.add(nu)
        out.append(full)
    return out


def find_lot_title(soup: BeautifulSoup) -> str:
    """Заголовок лота с детальной страницы (не имя сайта).
    Приоритет: <h1> → og:title → <title> (до разделителя)."""
    h1 = soup.find("h1")
    if h1:
        t = A.clean(h1.get_text(" ", strip=True))
        if t:
            return t
    og = soup.find("meta", attrs={"property": "og:title"})
    if og and og.get("content"):
        t = A.clean(og["content"])
        if t:
            return t
    if soup.title and soup.title.string:
        t = A.clean(soup.title.string)
        # отрезаем хвост вида « — Konfiskat.by» / « | konfiskat.by»
        t = re.split(r"\s*[|—\-–]\s*", t)[0].strip()
        if t and "konfiskat" not in t.lower():
            return t
    return ""


def detail_text(soup: BeautifulSoup) -> str:
    """Чистый текст детальной страницы (без script/style) для хелперов A.*."""
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return A.clean(soup.get_text(" ", strip=True))


def parse_detail(url: str, html: str) -> dict | None:
    soup = soup_of(html)
    title = find_lot_title(soup)
    if not title:
        return None
    text = detail_text(soup)
    nu = A.norm_url(url)

    it = A.blank_item(SOURCE)
    it["Тип торгов"] = "Аукцион"
    it["Объект"] = title
    it["Ссылка"] = nu

    # цена / дата
    it["Начальная цена"] = A.extract_start_price(text)
    it["Дата аукциона"] = A.parse_date(text)

    # задаток (сумма обычно после слова)
    mz = re.search(
        r"[Зз]адат\w+.{0,80}?(\d[\d\s]*[.,]?\d*)\s*(?:BYN|бел\.?\s*руб|Br)", text
    )
    if mz:
        it["Задаток"] = A.parse_price(mz.group(0))

    # адрес: сперва из заголовка+начала текста, чтобы не цеплять мусор со всей страницы
    blob = title + ". " + text[:1500]
    addr = A.extract_address(blob) or A.extract_address(text)
    if addr:
        it["Адрес"] = addr
    if re.search(r"минск", blob, re.I):
        it["Район / Город"] = "г. Минск"

    # площадь: из заголовка, иначе из текста
    area = A.extract_area(title) or A.extract_area(text)
    it["Площадь, м²"] = str(area) if area else ""

    # организатор
    mo = re.search(r"(?i)организатор[:\s\-]*([^\n.]{5,80})", text)
    if mo:
        it["Организатор"] = A.clean(mo.group(1))

    # телефон — по сырому HTML (хелпер сам нормализует)
    it["Телефон"] = A.extract_phones(html)

    it["Хэш"] = A.make_hash(nu, it["Объект"])
    return it


def collect_lot_urls() -> list[str]:
    """Обходит пагинацию списка (Bitrix PAGEN_1), собирает все URL лотов."""
    urls: list[str] = []
    seen: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        if page == 1:
            url = LIST_URL
        else:
            sep = "&" if "?" in LIST_URL else "?"
            url = f"{LIST_URL}{sep}PAGEN_1={page}"
        print(f"[KONFISKAT] список стр.{page}: {url}")
        html = A.fetch(url)
        if not html:
            break
        links = find_lot_links(soup_of(html))
        new_on_page = 0
        for full in links:
            nu = A.norm_url(full)
            if nu in seen:
                continue
            seen.add(nu)
            urls.append(full)
            new_on_page += 1
        print(f"  ссылок на странице: {len(links)} (новых: {new_on_page})")
        # конец пагинации: пусто ИЛИ все ссылки уже видели
        if new_on_page == 0:
            break
        time.sleep(random.uniform(1.0, 2.0))
    return urls


def parse_konfiskat() -> list[dict]:
    items: list[dict] = []
    urls = collect_lot_urls()
    print(f"[KONFISKAT] всего ссылок лотов: {len(urls)}")
    for full in urls:
        dhtml = A.fetch(full)
        if not dhtml:
            continue
        it = parse_detail(full, dhtml)
        if not it:
            continue
        items.append(it)
        print(
            f"  + {it['Дата аукциона'] or '????'} | {it['Объект'][:45]} | "
            f"{it['Начальная цена'] or '—'}"
        )
        time.sleep(random.uniform(1.0, 2.0))
    return items


if __name__ == "__main__":
    res = parse_konfiskat()
    print(f"\n[KONFISKAT] лотов: {len(res)}")
    if res:
        for c in A.AUCTION_COLUMNS:
            n = sum(1 for r in res if r.get(c))
            print(f"  {c:18}: {n}/{len(res)} ({100 * n // len(res)}%)")
    A.write_excel(res, Path("auctions_konfiskat.xlsx"))

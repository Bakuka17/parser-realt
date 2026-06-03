"""beltorgi_auctions — парсер аукционов ЗАО «Белреализация» (beltorgi.by).

Площадка по торгам имуществом банкротов. Список лотов на /aukciony/ грузится через
AJAX (POST /assets/display/), поэтому листинг снимаем Playwright-ом (рендер DOM).
Детальная страница лота — lot-{id}-{n}.html — СЕРВЕРНАЯ (берётся обычным GET):
  • хлебная крошка «Аукционы › <Категория> › <Заголовок>» — по <Категория> определяем
    недвижимость (на сайте раздел «Недвижимость» / «Коммерческая недвижимость - офисы/производство»);
  • h1 — объект; «Адрес: …»; «Задаток … в размере - N бел.руб»; организатор; телефон.
  ⚠ СТАРТОВАЯ ЦЕНА на деталке динамическая (грузится JS на «живом» аукционе) — в статике
    её часто нет, поэтому «Начальная цена» best-effort (может быть пустой).

Площадка СМЕШАННАЯ (авто, спецтехника, станки, долги) — берём ТОЛЬКО лоты, у которых
категория в хлебной крошке = недвижимость. На момент написания активной недвижимости 0,
но парсер автоматически подхватит её, когда появится.

Запуск:  ./bin/python beltorgi_auctions.py
"""
from __future__ import annotations

import re
import time
import random
import ssl
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

import auctions_common as A

SOURCE = "beltorgi.by"
BASE = "https://beltorgi.by"
# Активные торги (status 1,6,8) + несостоявшиеся, ожидающие повторных (4,5,12,13) —
# имущество там всё ещё продаётся, это валидные лиды.
LISTINGS = [
    "https://beltorgi.by/aukciony/?status=1,6,8",
    "https://beltorgi.by/aukciony/?status=4,5,12,13",
]
LOT_RE = re.compile(r"lot-\d+-\d+\.html")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_SSL = ssl.create_default_context(); _SSL.check_hostname = False; _SSL.verify_mode = ssl.CERT_NONE

# Категория недвижимости в хлебной крошке.
RE_CAT = re.compile(r"недвиж|помещени|здани|квартир|земель|\bземл|офис|склад|производ", re.I)


def _get(url: str, timeout: int = 25) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ru,en"})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"    ✖ GET {url}: {e}")
        return ""


def collect_lot_urls() -> list[str]:
    """Рендерит листинги Playwright-ом, собирает уникальные ссылки lot-*.html."""
    urls: list[str] = []
    seen: set[str] = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=UA)
        for listing in LISTINGS:
            try:
                page.goto(listing, wait_until="networkidle", timeout=45000)
                page.wait_for_timeout(2500)
            except Exception as e:  # noqa: BLE001
                print(f"  ✖ рендер {listing}: {e}"); continue
            hrefs = page.eval_on_selector_all(
                "a[href*='lot-']", "els => els.map(e => e.getAttribute('href'))"
            )
            n = 0
            for h in hrefs:
                if not h or not LOT_RE.search(h):
                    continue
                full = h if h.startswith("http") else BASE + "/" + h.lstrip("/")
                nu = A.norm_url(full)
                if nu in seen:
                    continue
                seen.add(nu); urls.append(full); n += 1
            print(f"  {listing} → лотов в DOM: {n}")
        browser.close()
    return urls


def breadcrumb_category(soup: BeautifulSoup) -> str:
    """Категория(и) лота из хлебной крошки «Аукционы › <Категория> › <Заголовок>».
    Возвращает все крошки КРОМЕ последней (заголовка лота), склеенные — по ним
    матчим недвижимость. Берём текст <li> (не вложенных <a>, иначе дубли)."""
    crumb = soup.select_one(".breadcrumb, [class*=breadcrumb]")
    if not crumb:
        return ""
    items = [A.clean(li.get_text(" ", strip=True)) for li in crumb.find_all("li")]
    items = [x for x in items if x]
    if not items:
        items = [A.clean(a.get_text(" ", strip=True)) for a in crumb.find_all("a") if a.get_text(strip=True)]
    # дедуп подряд идущих (вложенные li>a дают повтор)
    dedup: list[str] = []
    for x in items:
        if not dedup or dedup[-1] != x:
            dedup.append(x)
    # последняя крошка — заголовок лота; категория — всё до неё
    return " ".join(dedup[:-1]) if len(dedup) >= 2 else (dedup[0] if dedup else "")


def parse_detail(url: str, html: str) -> dict | None:
    soup = BeautifulSoup(html, "lxml")
    cat = breadcrumb_category(soup)
    h1 = soup.find("h1")
    title = A.clean(h1.get_text(" ", strip=True)) if h1 else ""
    # фильтр недвижимости: по категории-крошке, иначе по заголовку
    if not (RE_CAT.search(cat) or RE_CAT.search(title)):
        return None
    if not title:
        return None

    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    nu = A.norm_url(url)

    it = A.blank_item(SOURCE)
    it["Тип торгов"] = "Аукцион"
    it["Объект"] = title
    it["Ссылка"] = nu

    # адрес: «Адрес: …»
    ma = re.search(r"Адрес[:\s]+([^\n]{5,90}?)(?:\s*Показать|\s*C\s+НДС|\s*Без\s+НДС|$)", text, re.I)
    addr = ""
    if ma:
        addr = A.extract_address(ma.group(1)) or A.clean(ma.group(1))
    if not addr:
        addr = A.extract_address(text) or ""
    it["Адрес"] = addr
    mcity = re.search(r"г\.\s*([А-ЯЁ][а-яё-]+)", addr or title)
    if mcity:
        it["Район / Город"] = "г. " + mcity.group(1)

    it["Площадь, м²"] = (lambda a: str(a) if a else "")(A.extract_area(title) or A.extract_area(text))

    # цена — best-effort (на деталке часто динамическая)
    it["Начальная цена"] = A.extract_start_price(text)

    # задаток: «Задаток … в размере - 250,00 бел. руб»
    mz = re.search(r"задат\w*.{0,40}?(\d[\d ]*[.,]?\d*)\s*(?:бел\.?\s*руб|BYN|руб|Br)", text, re.I)
    if mz:
        it["Задаток"] = A.parse_price(mz.group(0))

    # дата — прицельно у слов про торги/аукцион (не первая попавшаяся)
    md = re.search(r"(?:дата|торг\w*|аукцион\w*|проведени\w*)[^\d]{0,25}(\d{1,2}[.\-/]\d{1,2}[.\-/]\d{4})", text, re.I)
    if md:
        it["Дата аукциона"] = A.parse_date(md.group(1))

    # организатор: «Организатор торгов Наименование <X> Контактное лицо»
    mo = re.search(r"Организатор\s+торгов\s+Наименование\s+(.+?)\s+(?:Контакт|УНП|Адрес|Тел)", text, re.I)
    if mo:
        it["Организатор"] = A.clean(mo.group(1))[:80]

    it["Телефон"] = A.extract_phones(html)
    it["Хэш"] = A.make_hash(nu, it["Объект"])
    return it


def parse_beltorgi() -> list[dict]:
    print(f"🔨 beltorgi_auctions | источник: {SOURCE}")
    urls = collect_lot_urls()
    print(f"  всего ссылок лотов: {len(urls)} — фильтрую недвижимость по хлебной крошке…")
    items: list[dict] = []
    for i, url in enumerate(urls, 1):
        html = _get(url)
        if not html:
            continue
        it = parse_detail(url, html)
        if it:
            items.append(it)
            print(f"  [{i}/{len(urls)}] 🏠 + {it['Объект'][:50]} | {it['Начальная цена'] or '—'}")
        time.sleep(random.uniform(0.8, 1.6))
    return items


if __name__ == "__main__":
    res = parse_beltorgi()
    print(f"\n[BELTORGI] лотов недвижимости: {len(res)}")
    if res:
        for c in A.AUCTION_COLUMNS:
            n = sum(1 for r in res if r.get(c))
            print(f"  {c:18}: {n}/{len(res)} ({100 * n // len(res)}%)")
    else:
        print("  (активной недвижимости сейчас нет — площадка смешанная, "
              "недвиж-разделы пусты; парсер подхватит лоты, когда появятся)")
    A.write_excel(res, Path("auctions_beltorgi.xlsx"))

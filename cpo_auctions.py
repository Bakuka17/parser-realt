"""cpo_auctions — парсер аукционов недвижимости cpo.by (Центр поддержки предпринимательства, Bitrix).

Серверный HTML. Фильтр недвижимости /auctions/filter/section-is-nedvizhimost/apply/ (как ipmtorgi).
Карточки sales__item содержат всё в листинге: заголовок, дату аукциона, город, адрес,
начальную цену (BYN). Пагинация ?PAGEN_1=N. Деталь лота — телефон/площадь (бережно).

Запуск:  ./bin/python cpo_auctions.py
"""
import os
import random
import re
import time
from pathlib import Path

import auctions_common as A

BASE = "https://www.cpo.by"
LIST = BASE + "/auctions/filter/section-is-nedvizhimost/apply/"
CHECKPOINT_EVERY = 20


def get_text(html: str) -> str:
    if not html:
        return ""
    t = re.sub(r"<script.*?</script>", "", html, flags=re.S | re.I)
    t = re.sub(r"<style.*?</style>", "", t, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    import html as _h
    return re.sub(r"\s+", " ", _h.unescape(t)).strip()


def parse_cards(html: str) -> list[dict]:
    """Карточки sales__item → поля из листинга. Заголовок — первый осмысленный текст
    карточки (не служебная метка)."""
    cards = []
    # карточка = блок data-entity="item" (НЕ sales__item — у него есть под-классы
    # sales__item-img/-text, по ним split рвёт карточку в труху). ~9 карточек на странице.
    # Поля берём из ОЧИЩЕННОГО текста карточки (в сыром HTML цена рвётся на &nbsp;).
    for seg in re.split(r'data-entity="item"', html)[1:]:
        seg = seg[:4000]
        ml = re.search(r'href="(https://www\.cpo\.by/auctions/(?!filter)[^"/]+/)"', seg)
        if not ml:
            continue
        t = get_text(seg)   # «Недвижимость ЗАГОЛОВОК Дата аукциона: ДД.ММ.ГГГГ ГОРОД АДРЕС Начальная цена … N BYN …»
        mt = re.search(r'Недвижимост\w*\s+(.+?)\s+Дата\s+аукциона', t)
        title = re.sub(r'^(?:Цена снижена\s*)+', '', A.clean(mt.group(1))).strip() if mt else ""
        mdate = re.search(r'Дата\s+аукциона:?\s*(\d{2}\.\d{2}\.\d{4})', t)
        maddr = re.search(r'([А-ЯЁ][а-яё]+\s+обл\..+?)(?:\s+Начальн|\s+Задат|$)', t)
        mprice = re.search(r'Начальн\w*\s*цен\w*[^\d]{0,40}(\d[\d\s.,]*\d)\s*BYN', t)
        cards.append({
            "link": ml.group(1),
            "title": title,
            "date": A.parse_date(mdate.group(1)) if mdate else "",
            "addr": A.clean(maddr.group(1)) if maddr else "",
            "price": (mprice.group(1) + " BYN") if mprice else "",
        })
    return cards


def _next_page(html: str, page: int) -> bool:
    return f"PAGEN_1={page + 1}" in html


def collect(skip_urls: set, on_checkpoint=None) -> list[dict]:
    new, seen = [], set()
    for page in range(1, 60):
        url = LIST if page == 1 else f"{LIST}?PAGEN_1={page}"
        print(f"[CPO] стр.{page}")
        html = A.fetch(url)
        if not html:
            break
        cards = parse_cards(html)
        if not cards:
            break
        fresh = 0
        for card in cards:
            nu = A.norm_url(card["link"])
            if nu in seen or nu in skip_urls:
                continue
            seen.add(nu); fresh += 1
            it = A.blank_item("cpo.by")
            it["Тип торгов"] = "Аукцион"
            it["Объект"] = card["title"] or "Объект недвижимости"
            it["Адрес"] = card["addr"]
            mcity = re.search(r'г\.\s*([А-ЯЁ][а-яё-]+)', card["addr"])
            it["Район / Город"] = mcity.group(1) if mcity else ""
            it["Начальная цена"] = A.parse_price(card["price"])
            it["Дата аукциона"] = card["date"]
            it["Ссылка"] = nu
            it["Описание"] = card["title"]
            dhtml = A.fetch(card["link"])
            if dhtml:
                dtext = get_text(dhtml)
                ar = A.extract_area(dtext)
                it["Площадь, м²"] = str(ar) if ar else ""
                it["Телефон"] = A.extract_phones(dhtml)
                md = re.search(r'(?i)задат\w+.{0,50}?(\d[\d\s.,]*)\s*(?:BYN|руб)', dtext)
                it["Задаток"] = A.parse_price(md.group(0)) if md else ""
                if not it["Начальная цена"]:   # цены не было в листинге — берём с детали
                    it["Начальная цена"] = A.extract_start_price(dtext)
            it["Хэш"] = A.make_hash(nu, it["Объект"])
            new.append(it)
            print(f"  + {it['Объект'][:42]} | {it['Начальная цена'] or '—'} | {it['Дата аукциона'] or '—'}")
            if on_checkpoint and len(new) % CHECKPOINT_EVERY == 0:
                on_checkpoint(new)
            time.sleep(random.uniform(0.8, 1.6))
        if fresh == 0 and not _next_page(html, page):
            break
        if not _next_page(html, page):
            break
    return new


def main():
    out = Path("auctions_cpo.xlsx").resolve()
    tmp = out.with_suffix(".tmp.xlsx")
    base = A.load_prev(tmp) if tmp.exists() else {}
    base_vals = list(base.values())
    skip_urls = set(base.keys())
    snapshot = {str(r.get("Хэш")) for r in base.values() if r.get("Хэш")}

    def save(items, final=False):
        A.write_excel(base_vals + items, tmp, prev_hashes=snapshot)
        if final:
            os.replace(tmp, out)

    new = collect(skip_urls, on_checkpoint=lambda items: save(items))
    print(f"\n[CPO] всего: {len(base_vals) + len(new)} (новых: {len(new)})")
    save(new, final=True)
    res = base_vals + new
    if res:
        for c in ("Объект", "Начальная цена", "Адрес", "Дата аукциона", "Площадь, м²", "Телефон"):
            n = sum(1 for r in res if r.get(c))
            print(f"  {c:16}: {n}/{len(res)} ({100*n//len(res)}%)")


if __name__ == "__main__":
    main()

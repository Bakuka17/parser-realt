"""belinvest_bank — парсер залоговой/непрофильной недвижимости Белинвестбанка.

Банки РБ реализуют недвижимость должников/непрофиль. Белинвестбанк — самый богатый
источник (серверный HTML): на странице каталога ~35 объектов в блоках с
data-category-name="Недвижимость" — цена (min … руб), район, тип (из слага ссылки),
дата размещения. Деталь объекта даёт телефон/фото (шумная, берём бережно).

Это НЕ аукцион (прямая продажа банком), но поля совпадают со схемой AUCTION_COLUMNS —
переиспользуем её; «Тип торгов» = «Продажа банком», «Дата аукциона» пустая.

ponytail: данные листинга чище детали (h1 общий, страница 340КБ) — основное берём из
листинга, в деталь ходим только за телефоном объекта (иначе общий телефон банка).

Запуск:  ./bin/python belinvest_bank.py
"""
import os
import random
import re
import time
from pathlib import Path

import auctions_common as A

BASE = "https://www.belinvestbank.by"
LIST_URL = BASE + "/about-bank/page/realizacziya-zalozhennogo-nedvizhimogo-imustchestva"
BANK_PHONE = "+375 17 239-02-39"   # горячая линия Белинвеста по реализации (фолбэк)
CHECKPOINT_EVERY = 20


def _title_from_slug(slug: str) -> str:
    """proizvodstvennoe-zdanie-mozyrskij-r-n → 'Proizvodstvennoe zdanie mozyrskij r n' —
    но лучше брать русский заголовок из блока; слаг лишь фолбэк."""
    return slug.replace("-", " ").strip().capitalize()


def parse_listing(html: str) -> list[dict]:
    """Из каталога → карточки объектов недвижимости (блоки data-category-name='Недвижимость')."""
    cards = []
    for blk in re.split(r'data-category-name="Недвижимость"', html)[1:]:
        mlink = re.search(r'href="(/about-bank/catalog/[^"]*?nedvizhimost/[^"]+)"', blk)
        if not mlink:
            continue
        link = BASE + mlink.group(1)
        slug = mlink.group(1).rstrip("/").split("/")[-1]
        # читаемый заголовок объекта из текста ссылки, иначе из слага
        mt = re.search(r'js-template-page-name[^>]*>(.*?)<', blk, re.S)
        title = A.clean(mt.group(1)) if mt and A.clean(mt.group(1)) else _title_from_slug(slug)
        mprice = re.search(r'(?:min\s*)?(\d[\d\s\xa0]{3,}(?:[.,]\d{2})?)\s*руб', blk, re.I)
        # район/город: короткий фрагмент с «р-н»/«г.»/«обл»
        bt = A.get_text(blk)
        mreg = re.search(r'([А-ЯЁ][а-яё]+(?:ский|ская|ний)?\s*(?:р-н|район|обл\.?|область)'
                         r'|г\.\s*[А-ЯЁ][а-яё-]+)', bt)
        mdate = re.search(r'data-page-date="(\d{4})(\d{2})(\d{2})', blk)
        cards.append({
            "link": link, "slug": slug, "title": title,
            "price": mprice.group(0) if mprice else "",
            "region": A.clean(mreg.group(0)) if mreg else "",
            "date": f"{mdate.group(1)}-{mdate.group(2)}-{mdate.group(3)}" if mdate else "",
        })
    # дедуп по ссылке
    seen, out = set(), []
    for c in cards:
        nu = A.norm_url(c["link"])
        if nu not in seen:
            seen.add(nu); out.append(c)
    return out


def collect(skip_urls: set, on_checkpoint=None) -> list[dict]:
    print("[BELINVEST] каталог недвижимости…")
    html = A.fetch(LIST_URL)
    if not html:
        return []
    cards = parse_listing(html)
    print(f"[BELINVEST] объектов: {len(cards)}")
    new = []
    for card in cards:
        nu = A.norm_url(card["link"])
        if nu in skip_urls:
            continue
        it = A.blank_item("belinvestbank.by")
        it["Тип торгов"] = "Продажа банком"
        it["Объект"] = card["title"] or "Объект недвижимости"
        it["Адрес"] = card["region"]
        it["Район / Город"] = card["region"]
        it["Начальная цена"] = A.parse_price(card["price"])
        it["Ссылка"] = nu
        it["Источник"] = "belinvestbank.by"
        it["Описание"] = card["title"]
        # деталь: телефон объекта + площадь + фото (бережно — страница шумная)
        dhtml = A.fetch(card["link"])
        if dhtml:
            dtext = A.get_text(dhtml)
            ar = A.extract_area(dtext)
            it["Площадь, м²"] = str(ar) if ar else ""
            ph = A.extract_phones(dhtml)
            it["Телефон"] = ph or BANK_PHONE
            mph = re.search(r'(https?://[^"\']+?\.(?:jpg|jpeg|png))', dhtml, re.I)
            it["Фото URL"] = mph.group(1) if mph else ""
        else:
            it["Телефон"] = BANK_PHONE
        it["Хэш"] = A.make_hash(nu, it["Объект"])
        new.append(it)
        print(f"  + {it['Объект'][:40]} | {it['Начальная цена'] or '—'} | {it['Район / Город'] or '—'}")
        if on_checkpoint and len(new) % CHECKPOINT_EVERY == 0:
            on_checkpoint(new)
        time.sleep(random.uniform(0.8, 1.6))
    return new


def main():
    out = Path("banks_belinvest.xlsx").resolve()
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
    print(f"\n[BELINVEST] всего: {len(base_vals) + len(new)} (новых: {len(new)})")
    save(new, final=True)
    res = base_vals + new
    if res:
        for c in ("Объект", "Начальная цена", "Район / Город", "Площадь, м²", "Телефон", "Ссылка"):
            n = sum(1 for r in res if r.get(c))
            print(f"  {c:16}: {n}/{len(res)} ({100*n//len(res)}%)")


if __name__ == "__main__":
    main()

"""fcon_auctions — парсер аукционов недвижимости fcon.by (ЭТП «Фонд», JoomShopping).

Серверный HTML. Листинг /auctions/nedvizhimost отдаёт карточки лотов (blockProductItemLot)
с заголовком (тип+город+площадь), адресом (auctionAddress title), датой аукциона и фото.
Детальная страница лота даёт начальную цену, задаток, телефон, полное фото.

ponytail: берём первую страницу листинга (~26 лотов). Доп. лоты fcon подгружает AJAX-кнопкой
«productsAuctionMore» — если понадобится глубже, реверснуть её эндпоинт (пока YAGNI: первой
страницы хватает, лоты сортированы свежими сверху).

Чекпойнты+резюм как у ipmtorgi/mgcn: .tmp.xlsx каждые N лотов, финал — атомарный os.replace.

Запуск:  ./bin/python fcon_auctions.py
"""
import os
import random
import re
import time
from datetime import date
from pathlib import Path

import auctions_common as A

BASE = "https://fcon.by"
LIST_URL = BASE + "/auctions/nedvizhimost"
CHECKPOINT_EVERY = 20
# fcon по недвижимости показывает в осн. АРХИВ (не состоялись/продано/отменён). Для лидгена
# берём только АКТУАЛЬНЫЕ лоты: статус не «завершён/продано/отменён» И дата не в прошлом.
# Сейчас актуальных 0 (как beltorgi) — парсер подхватит, когда fcon выставит новые торги.
_ARCHIVE_RX = re.compile(r"не\s+состоял|продано|отмен|заверш", re.I)
_TODAY = date.today().isoformat()

_PRICE_RE = re.compile(r"начальн\w*\s*цен\w*\s*:?\s*([\d\s.,]+?)\s*(?:BYN|бел|руб|Br)", re.I)
_DEP_RE = re.compile(r"задатк\w*\s*:?\s*([\d\s.,]+?)\s*(?:BYN|бел|руб|Br)", re.I)


def _city(addr: str) -> str:
    """Населённый пункт из адреса: 'г. Житковичи, ул...' → 'Житковичи'."""
    m = re.search(r"(?:г\.|аг\.|гп\.|д\.|г\.п\.)\s*([А-ЯЁ][а-яё-]+)", addr or "")
    return m.group(1) if m else ""


def parse_cards(listing_html: str) -> list[dict]:
    """Из листинга → карточки с тем, что видно сразу (ссылка/заголовок/адрес/дата/лот/фото).
    Разбиваем по data-type="lot" — каждый сегмент содержит одну карточку лота."""
    cards = []
    for seg in re.split(r'data-type="lot"', listing_html)[1:]:
        mlink = re.search(r'href="(/auctions/nedvizhimost/[^"]+)"', seg)
        if not mlink:
            continue
        mt = re.search(r'moduleProductName.*?title="([^"]+)"', seg, re.S)
        maddr = re.search(r'auctionAddress"\s+title="([^"]+)"', seg)
        mdate = re.search(r"Дата аукциона:\s*<b>\s*([\d.]+)", seg)
        mlot = re.search(r"Лот\s*№\s*([0-9A-Za-zА-Яа-я\-]+)", seg)
        mphoto = re.search(r'(https://fcon\.by/[^"]*?img_products/[^"]+\.jpe?g)', seg)
        mstatus = re.search(r'listLotStatus[^>]*>\s*([^<]+?)\s*<', seg)
        cards.append({
            "link": BASE + mlink.group(1),
            "title": A.clean(mt.group(1)) if mt else "",
            "addr": A.clean(maddr.group(1)) if maddr else "",
            "date": A.parse_date(mdate.group(1)) if mdate else "",
            "lot": mlot.group(1) if mlot else "",
            "photo": mphoto.group(1).replace("thumb_", "full_") if mphoto else "",
            "status": A.clean(mstatus.group(1)) if mstatus else "",
        })
    return cards


def _is_archive(card: dict) -> bool:
    """Завершённый/проданный/отменённый лот или прошедшая дата — для лидгена не нужен."""
    return bool(_ARCHIVE_RX.search(card["status"])) or bool(card["date"] and card["date"] < _TODAY)


def collect(skip_urls: set, on_checkpoint=None) -> list[dict]:
    """Собирает лоты недвижимости fcon, пропуская URL из skip_urls (резюм после обрыва)."""
    new = []
    print("[FCON] листинг недвижимости…")
    listing = A.fetch(LIST_URL)
    if not listing:
        return new
    cards = parse_cards(listing)
    actual = [c for c in cards if not _is_archive(c)]
    print(f"[FCON] карточек: {len(cards)}, актуальных (предстоящих): {len(actual)} — архив пропущен")
    for card in actual:
        nu = A.norm_url(card["link"])
        if nu in skip_urls:
            continue
        dhtml = A.fetch(card["link"])
        if not dhtml:
            continue
        text = A.get_text(dhtml)
        it = A.blank_item("fcon.by")
        it["Ссылка"] = nu
        it["Тип торгов"] = "Электронные торги"
        it["Объект"] = card["title"]
        if not it["Объект"]:
            continue
        it["Адрес"] = card["addr"]
        it["Район / Город"] = _city(card["addr"])
        ar = A.extract_area(card["title"]) or A.extract_area(text)
        it["Площадь, м²"] = str(ar) if ar else ""
        mp = _PRICE_RE.search(text)
        it["Начальная цена"] = A.parse_price(mp.group(0)) if mp else A.extract_start_price(text)
        md = _DEP_RE.search(text)
        it["Задаток"] = A.parse_price(md.group(0)) if md else ""
        it["Дата аукциона"] = card["date"] or A.parse_date(text)
        it["Телефон"] = A.extract_phones(text)
        it["Фото URL"] = card["photo"]
        it["Описание"] = card["title"]   # ponytail: заголовок информативен (тип+город+площадь); полный текст JoomShopping — мусорный без bs4
        it["Хэш"] = A.make_hash(nu, card["lot"] or it["Объект"])
        new.append(it)
        print(f"  + {it['Объект'][:45]} | цена={it['Начальная цена'] or '—'} | {it['Дата аукциона'] or '—'}")
        if on_checkpoint and len(new) % CHECKPOINT_EVERY == 0:
            on_checkpoint(new)
        time.sleep(random.uniform(1.0, 2.0))
    return new


def main():
    out = Path("auctions_fcon.xlsx").resolve()
    tmp = out.with_suffix(".tmp.xlsx")
    base = A.load_prev(tmp) if tmp.exists() else {}
    if base:
        print(f"♻ найден чекпойнт ({len(base)} лотов) — продолжаю с него")
    base_vals = list(base.values())
    skip_urls = set(base.keys())
    snapshot = {str(r.get("Хэш")) for r in base.values() if r.get("Хэш")}

    def save(items: list[dict], final: bool = False) -> None:
        A.write_excel(base_vals + items, tmp, prev_hashes=snapshot)
        if final:
            os.replace(tmp, out)
        else:
            print(f"  💾 чекпойнт: всего {len(base_vals) + len(items)} (новых {len(items)})")

    new = collect(skip_urls, on_checkpoint=lambda items: save(items))
    print(f"\n[FCON] лотов: {len(base_vals) + len(new)} (новых: {len(new)})")
    save(new, final=True)
    res = base_vals + new
    if res:
        for c in A.AUCTION_COLUMNS:
            n = sum(1 for r in res if r.get(c))
            print(f"  {c:18}: {n}/{len(res)} ({100 * n // len(res)}%)")


if __name__ == "__main__":
    main()

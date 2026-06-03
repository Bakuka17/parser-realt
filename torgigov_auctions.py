"""torgigov_auctions — парсер ЕДИНОЙ СИСТЕМЫ ЭЛЕКТРОННЫХ ТОРГОВ (torgi.gov.by).

Сайт — SPA, но за ним чистый JSON-API: https://api.torgi.gov.by/api/lots?category=1&page=N
(category=1 = «Недвижимость»; ответ: result.lots[], result.totCnt). На момент написания
в недвижимости 365 активных лотов из 33392 за всю историю.

⚠ Сервер НЕ фильтрует по активному состоянию (state=строка → 500, int не даёт нужного).
НО лоты отсортированы по auctionStart УБЫВАНИЮ → активные («AuctionPublished» /
«AuctionPublishedEgrsb», торги ещё впереди) идут ПЕРВЫМИ. Поэтому пагинируем с page=1,
берём только активные состояния и останавливаемся, когда активные кончились
(несколько страниц подряд без активных — дальше только Sold/NotSold/Rejected).

Поля берём прямо из JSON листинга (доп. запрос детали не нужен):
  name→Объект, location→Адрес, initialPrice→Начальная цена, attributes[Площадь]→Площадь,
  auctionStart (.NET ticks)→Дата. Организатор отдаётся лишь id (имя/телефон API не отдаёт) —
  оставляем пустыми (торги ведутся через площадку, как у kufar).

Запуск:  ./bin/python torgigov_auctions.py
"""
from __future__ import annotations

import json
import ssl
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import auctions_common as A

SOURCE = "torgi.gov.by"
API = "https://api.torgi.gov.by/api/lots"
WEB_LOT = "https://torgi.gov.by/lot/{id}"          # человекочитаемый URL лота (SPA)
RE_CATEGORY = 1                                     # «Недвижимость»
ACTIVE_STATES = {"AuctionPublished", "AuctionPublishedEgrsb"}
STOP_AFTER_EMPTY_PAGES = 3                          # стоп: столько страниц подряд без активных
MAX_PAGES = 60                                      # предохранитель
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
_SSL = ssl.create_default_context(); _SSL.check_hostname = False; _SSL.verify_mode = ssl.CERT_NONE


def api_get(url: str, tries: int = 5, timeout: int = 25) -> dict | None:
    """GET JSON с ретраем на 429 (бэкофф)."""
    for k in range(tries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json",
                              "Referer": "https://torgi.gov.by/"})
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:  # noqa: PERF203
            if e.code == 429:
                time.sleep(3 * (k + 1)); continue
            print(f"    ✖ {url}: HTTP {e.code}"); return None
        except Exception as e:  # noqa: BLE001
            print(f"    ✖ {url}: {e}"); return None
    print(f"    ✖ {url}: 429 (исчерпаны ретраи)"); return None


def ticks_to_date(ticks) -> str:
    """.NET ticks (100-нс с 0001-01-01) → 'YYYY-MM-DD'. 0/None → ''."""
    try:
        t = int(ticks)
        if t <= 0:
            return ""
        return (datetime(1, 1, 1) + timedelta(microseconds=t // 10)).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return ""


def area_from_attributes(lot: dict) -> str:
    for a in lot.get("attributes") or []:
        if "площад" in str(a.get("name", "")).lower():
            val = A.extract_area(str(a.get("value", "")))
            if val:
                return str(val)
    # фолбэк — из описания
    val = A.extract_area(lot.get("description", "") or "")
    return str(val) if val else ""


def city_from_location(loc: str) -> str:
    import re
    if not loc:
        return ""
    m = re.search(r"г\.?\s*([А-ЯЁ][а-яё-]+)", loc)
    if m:
        return "г. " + m.group(1)
    m = re.search(r"([А-ЯЁ][а-яё-]+)\s+район", loc)
    if m:
        return m.group(1) + " район"
    return ""


def lot_to_item(lot: dict) -> dict:
    it = A.blank_item(SOURCE)
    it["Тип торгов"] = "Электронные торги"
    it["Объект"] = A.clean(lot.get("name", ""))
    loc = A.clean(lot.get("location", ""))
    it["Адрес"] = A.extract_address(loc) or loc
    it["Район / Город"] = city_from_location(loc)
    it["Площадь, м²"] = area_from_attributes(lot)
    # initialPrice хранится в КОПЕЙКАХ (целое) — BYN = /100 (на сайте сумма с 2 знаками).
    kop = lot.get("initialPrice") or lot.get("currentInitialPrice") or 0
    it["Начальная цена"] = f"{kop / 100:.2f} BYN" if kop else ""
    it["Дата аукциона"] = ticks_to_date(lot.get("auctionStart"))
    # описание объекта (главное для torgi.gov) — без болванки про НДС
    it["Описание"] = A.clean_auction_description(lot.get("description", ""))
    # организатор/телефон API не отдаёт (только id) → пусто; контакт = ссылка на аукцион
    url = WEB_LOT.format(id=lot.get("id"))
    it["Ссылка"] = A.norm_url(url)
    it["Хэш"] = A.make_hash(url, it["Объект"])
    return it


def parse_torgigov() -> list[dict]:
    print(f"🔨 torgigov_auctions | источник: {SOURCE} (category={RE_CATEGORY}=Недвижимость)")
    items: list[dict] = []
    seen: set[str] = set()
    empty_streak = 0
    for page in range(1, MAX_PAGES + 1):
        j = api_get(f"{API}?category={RE_CATEGORY}&page={page}")
        if not j or not j.get("result"):
            break
        lots = j["result"].get("lots") or []
        if not lots:
            break
        active = [l for l in lots if l.get("state") in ACTIVE_STATES]
        for lot in active:
            nu = A.norm_url(WEB_LOT.format(id=lot.get("id")))
            if nu in seen:
                continue
            seen.add(nu)
            items.append(lot_to_item(lot))
        if page == 1:
            print(f"  всего в категории (история): {j['result'].get('totCnt')}")
        print(f"  стр.{page}: активных {len(active)}/{len(lots)} | накоплено {len(items)}")
        if not active:
            empty_streak += 1
            if empty_streak >= STOP_AFTER_EMPTY_PAGES:
                print(f"  ⏹ {STOP_AFTER_EMPTY_PAGES} стр. подряд без активных — активные кончились")
                break
        else:
            empty_streak = 0
        time.sleep(1.0)
    return items


if __name__ == "__main__":
    res = parse_torgigov()
    print(f"\n[TORGI.GOV] активных лотов недвижимости: {len(res)}")
    if res:
        for c in A.AUCTION_COLUMNS:
            n = sum(1 for r in res if r.get(c))
            print(f"  {c:18}: {n}/{len(res)} ({100 * n // len(res)}%)")
    A.write_excel(res, Path("auctions_torgigov.xlsx"))

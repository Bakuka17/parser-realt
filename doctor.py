#!/usr/bin/env python3
"""doctor.py — health-check источников перед сбором.

Один лёгкий запрос на источник → кто жив, кто лёг, доступны ли телефоны kufar
(зависит от страны IP). Не поднимает Playwright — голый urllib, ~5 секунд.

  ./bin/python doctor.py          # проверить источники
  ./bin/python doctor.py --test   # самопроверка логики (без сети)

Идея probe/doctor подсмотрена в Agent-Reach (github.com/Panniantong/Agent-Reach),
реализация наша — переиспользует fetch() из megapolis/kufar парсеров.
"""
import sys
import ssl
import json
import time
import urllib.request

from megapolis_parser import fetch as mp_fetch, BASE as MP_BASE, CATEGORIES as MP_CATS
from kufar_parser import extract_next_data

# ponytail: копия из realty_parser_v8 — импорт v8 тянет playwright, а зонд должен быть лёгким
BLOCK_MARKERS = ("cloudflare", "проверка безопасности", "доступ ограничен", "ddos",
                 "captcha", "attention required", "just a moment", "доступ запрещен",
                 "access denied")
UA = "Mozilla/5.0"
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def exit_country():
    """Страна внешнего IP -> (countryCode, country, ip).
    ponytail: 6 строк urllib, не тащим kufar_phones (он на playwright)."""
    try:
        with urllib.request.urlopen(
            "http://ip-api.com/json/?fields=country,countryCode,query", timeout=10
        ) as h:
            d = json.load(h)
        return d.get("countryCode"), d.get("country", "?"), d.get("query", "?")
    except Exception:
        return None, None, None


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20, context=_CTX) as h:
        return h.status, h.read().decode("utf-8", "ignore")


def realt_status(status, body):
    """Чистая логика: жив ли realt-листинг -> (ok, note). Тестируется в --test.
    Челлендж Cloudflare маленький и с маркером; настоящая страница ~700 КБ."""
    if status != 200:
        return False, f"HTTP {status}"
    low = body.lower()
    hit = next((m for m in BLOCK_MARKERS if m in low), None)
    if hit:
        return False, f"блокировка ({hit})"
    if len(body) < 100_000:
        return False, f"подозрительно мало ({len(body)//1024} КБ) — возможно челлендж"
    return True, f"{len(body)//1024} КБ, без блокировки"


def check_megapolis():
    url = f"{MP_BASE}/realt/{MP_CATS[0][0]}/"
    n = mp_fetch(url, retries=1).count('<section class="rItem')
    return (n > 0), (f"{n} объявлений на странице" if n else "0 секций — пусто/сменилась вёрстка")


def check_kufar():
    _, b = _get("https://re.kufar.by/l/minsk/snyat/kommercheskaya")
    data = extract_next_data(b) or {}
    ads = (data.get("props", {}).get("initialState", {})
               .get("listing", {}).get("ads") or [])
    return (len(ads) > 0), (f"{len(ads)} объявлений в листинге" if ads
                            else "нет данных в __NEXT_DATA__")


def check_realt():
    return realt_status(*_get("https://realt.by/sale/offices/"))


def check_gohome():
    _, b = _get("https://gohome.by/commerce/sale")
    n = b.count('class="w-object-list-item')
    return (n > 0), (f"{n} карточек на странице" if n else "0 карточек — пусто/сменилась вёрстка")


def check_byrealty():
    import re
    _, b = _get("https://byrealty.by/kommercheskaja-nedvizhimost/arenda")
    n = len(set(re.findall(r"/realty-(\d+)", b)))
    return (n > 0), (f"{n} объявлений в листинге" if n else "0 — пусто/сменилась вёрстка")


def run():
    cc, country, ip = exit_country()
    geo_ok = cc == "BY"
    print(f"\n  Здоровье источников · IP: {country} ({ip})"
          + ("" if geo_ok else "  ⚠ не Беларусь"))
    print("  " + "─" * 54)
    alive = 0
    checks = (("megapolis", check_megapolis), ("kufar", check_kufar),
              ("realt", check_realt), ("gohome", check_gohome), ("byrealty", check_byrealty))
    for name, fn in checks:
        t = time.time()
        try:
            ok, note = fn()
        except Exception as e:
            ok, note = False, f"НЕ ОТВЕЧАЕТ: {type(e).__name__} (возможно бан/TCP-дроп)"
        alive += ok
        print(f"  {'✅' if ok else '⛔'} {name:11} {note}   {time.time()-t:.1f}s")
    if not geo_ok:
        print("  ⚠ kufar-телефоны скрыты: нужен белорусский IP (Psiphon OFF) — kufar_phones.py")
    print(f"\n  Итог: {alive}/{len(checks)} источников отвечают.\n")
    return alive


def _test():
    assert realt_status(200, "x" * 200_000)[0] is True
    assert realt_status(200, "...Just a moment...")[0] is False     # челлендж
    assert realt_status(403, "x" * 200_000)[0] is False             # не 200
    assert realt_status(200, "x" * 5_000)[0] is False               # мелкая = подозрение
    assert realt_status(200, "x" * 200_000 + "CAPTCHA")[0] is False  # маркер в большой
    print("doctor self-test: OK (5/5)")


if __name__ == "__main__":
    _test() if "--test" in sys.argv else run()

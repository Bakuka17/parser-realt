#!/usr/bin/env python3
"""probe_1bv.py — разведчик источников недвижимости за 1 базовую величину (РБ).

⚠️ ЗАПУСКАТЬ С ВЫКЛЮЧЕННЫМ VPN/Psiphon (нужен белорусский IP — госреестры блокируют
иностранные IP отдачей 403). Скрипт автономный: Claude онлайн НЕ нужен.

Что делает: заходит на реестр ngi.gki.gov.by и областные комитеты госимущества,
сохраняет сырой HTML каждой страницы в папку probe_1bv/ и печатает сводку (что доступно,
есть ли каталог объектов/формы поиска). Потом Claude (под VPN) разберёт дампы и напишет парсер.

Порядок: 1) выключить VPN → 2) ./bin/python probe_1bv.py → 3) включить VPN → 4) вернуться
к Claude и показать вывод (или сказать «готово» — Claude прочитает probe_1bv/_summary.json).
"""
import json
import re
import ssl
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "probe_1bv"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# (имя файла, URL) — главный реестр + 6 областных комитетов госимущества.
TARGETS = [
    ("ngi_main",     "https://ngi.gki.gov.by/ru/"),
    ("ngi_registry", "https://ngi.gki.gov.by/ru/registry"),
    ("gki_main",     "https://www.gki.gov.by/ru/"),
    ("gomel",        "https://gomeloblim.gov.by/"),
    ("mogilev",      "https://mogilev-region.gov.by/category/investicionnyy-potencial-oblasti/neispolzuemye-obekty-nedvizhimosti"),
    ("minobl",       "https://minoblim.by/ru/"),
    ("vitebsk",      "https://www.fondgosim.vitebsk.by/lists.htm"),
    ("brest",        "https://brest-region.gov.by/ru/negosudarstvennoe-imushchestvo-305-ru/"),
]


def ip_country():
    """Страна внешнего IP -> (countryCode, country, ip)."""
    try:
        with urllib.request.urlopen(
            "http://ip-api.com/json/?fields=country,countryCode,query", timeout=10
        ) as h:
            d = json.load(h)
        return d.get("countryCode"), d.get("country", "?"), d.get("query", "?")
    except Exception:
        return None, None, None


def get(url, timeout=30):
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept-Language": "ru-RU,ru,be"})
    with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as h:
        return h.status, h.read().decode("utf-8", "ignore"), h.url


def analyze(html):
    """Грубые признаки каталога объектов в HTML — чтобы понять, что за страница."""
    low = html.lower()
    return {
        "len": len(html),
        "формы": low.count("<form"),
        "таблицы": low.count("<table"),
        "kw_1бв": len(re.findall(r"базов\w*\s*величин", low)),
        "kw_неиспольз": low.count("неиспольз"),
        "ссылок_объектов": len(set(re.findall(
            r'href="([^"]*(?:object|lot|detail|view|card|\?id=|nedvizhim)[^"]*)"', low))),
        "jsHeavy": low.count("<script") > 10 and (
            "react" in low or "__next" in low or "vue" in low),
    }


def main():
    OUT.mkdir(exist_ok=True)
    cc, country, ip = ip_country()
    print(f"IP: {country} ({ip})")
    if cc and cc != "BY":
        print(f"⚠ IP не белорусский ({cc}) — госреестры, скорее всего, отдадут 403.")
        print("  Выключите VPN/Psiphon и запустите снова, иначе данных не будет.\n")
    elif cc == "BY":
        print("✓ IP белорусский — госреестры должны открыться.\n")
    summary = [{"_probe_ip": ip, "_country": country, "_countryCode": cc}]
    for name, url in TARGETS:
        try:
            st, html, final = get(url)
            (OUT / f"{name}.html").write_text(html, encoding="utf-8")
            a = analyze(html)
            print(f"✅ {name:13} HTTP {st} {a['len']:>7}b | форм={a['формы']} табл={a['таблицы']} "
                  f"'1БВ'={a['kw_1бв']} объект-ссылок={a['ссылок_объектов']} js={int(a['jsHeavy'])}")
            summary.append({"name": name, "url": url, "final": final, "status": st, **a})
        except Exception as e:  # noqa: BLE001
            print(f"⛔ {name:13} ОШИБКА: {type(e).__name__}: {str(e)[:60]}")
            summary.append({"name": name, "url": url,
                            "error": f"{type(e).__name__}: {e}"})
    (OUT / "_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📁 Дампы в {OUT}/ — включите VPN, вернитесь к Claude, покажите вывод "
          "(или скажите «готово»: Claude прочитает probe_1bv/_summary.json).")


if __name__ == "__main__":
    main()

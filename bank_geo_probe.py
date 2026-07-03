"""bank_geo_probe — автономный разведзонд банков/агрегаторов, закрытых гео-блоком.

⚠ ЗАПУСКАТЬ БЕЗ VPN (белорусский IP): под иностранным IP эти сайты отдают
403/таймаут (проверено 03.07.2026). Зонд качает страницы и складывает HTML в
bank_geo_out/ + пишет отчёт. Ничего не парсит — по сохранённым страницам Claude
потом строит парсеры (как geo_probe.py для domovita/edc).

Запуск (Денис, VPN OFF):  ./bin/python bank_geo_probe.py
Потом VPN ON и вернуться к Claude — он заберёт bank_geo_out/.
"""
import socket
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "bank_geo_out"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
socket.setdefaulttimeout(20)

TARGETS = {
    # агрегаторы залогового имущества (главный приз — закрывают много банков разом)
    "benefit":     "https://benefit.by/realizuemoe-imuschestvo",
    "myfin":       "https://myfin.by/wiki/term/realizuemoe-imushhestvo",
    "ipmtorgi_banki": "https://www.ipmtorgi.by/services/realizaciya-imushestva-bankov",
    # банки, закрытые под VPN (403/timeout 03.07.2026)
    "rrb":         "https://www.rrb.by/bank/realizaciya-zalogovogo-bankovskogo-imushestva",
    "priorbank":   "https://www.priorbank.by/priorbank-main/realizable-property/nedvizimost",
    "belveb":      "https://www.belveb.by/realizuemoe-imushchestvo/",
    "mtbank":      "https://www.mtbank.by/about/property/",
    "paritet":     "https://www.paritetbank.by/about/realizatsiya-imushchestva/",
    "belarusbank": "https://belarusbank.by/o-banke/property/",
    "alfa":        "https://www.alfabank.by/about/selling/",
    "rbank":       "https://www.rbank.by/about/property/",
    "sber":        "https://www.sber-bank.by/property_sale/bank_property",
    "dabrabyt":    "https://bankdabrabyt.by/about/realizatsiya-imushchestva/",
    "belgazprom":  "https://belgazprombank.by/about/prodazha_imujestva/",
}


def main():
    OUT.mkdir(exist_ok=True)
    report = []
    for name, url in TARGETS.items():
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req) as r:
                html = r.read().decode("utf-8", "ignore")
            (OUT / f"{name}.html").write_text(html, encoding="utf-8")
            line = f"✅ {name:16s} {r.status} {len(html):>8} байт"
        except Exception as e:  # noqa: BLE001
            line = f"⛔ {name:16s} {type(e).__name__}: {str(e)[:70]}"
        print(line)
        report.append(f"{time.strftime('%Y-%m-%d %H:%M')} {line}  {url}")
        time.sleep(1.5)
    (OUT / "_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"\nГотово. Страницы и отчёт в {OUT}/ — включай VPN и возвращайся к Claude.")


if __name__ == "__main__":
    main()

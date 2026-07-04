"""bank_geo_probe2 — зонд-КРАУЛЕР для банков с глубоко запрятанными объектами.

⚠ ЗАПУСКАТЬ БЕЗ VPN (белорусский IP). В отличие от bank_geo_probe (качал по одному URL),
этот сам ходит ВГЛУБЬ: со стартовых страниц собирает ссылки про имущество/недвижимость
(+пагинацию) и обходит их BFS до 3 уровней, до 40 страниц на банк, пауза ~1с.
Всё складывает в bank_geo_out2/{банк}/ + _report.txt с метрикой «недвиж-слов/цен»
по каждой странице — по жирным страницам Claude строит парсеры.

Цели: Беларусбанк (объекты в /o-banke/property/bank-property/ и /client-property/,
внутри ещё категории), БНБ (раздел ищем от главной). Оба — гео-блок под VPN.

Запуск (Денис, VPN OFF):  ./bin/python bank_geo_probe2.py
Потом VPN ON и вернуться к Claude.
"""
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "bank_geo_out2"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}
socket.setdefaulttimeout(20)

# ссылки, по которым стоит идти вглубь
FOLLOW = re.compile(r"(?i)property|imush|realiz|prodazh|zalog|nedvizh|torg|auktsion|"
                    r"PAGEN|page=|section|catalog|arenda|[?&]id=\d+")
# страницы с этими словами считаем содержательными (метрика в отчёте)
RE_WORDS = re.compile(r"(?i)здание|помещение|квартир|гараж|склад|офис|недвижим|изолирован")
PRICE = re.compile(r"(?i)\d[\d\s\xa0’'.,]{3,}\s*(?:руб|BYN|бел)")

TARGETS = {
    "belarusbank": ["https://belarusbank.by/o-banke/property/bank-property/",
                    "https://belarusbank.by/o-banke/property/client-property/"],
    "bnb": ["https://www.bnb.by/", "https://bnb.by/"],
    # bc.by — наводка Дениса 04.07: аукционы + аренда (структура ссылок ?id=N)
    "bc": ["https://bc.by/?id=4", "https://bc.by/"],
}
MAX_PAGES = 40
MAX_DEPTH = 3


def fetch(url: str) -> str:
    # ⚠ грабля 04.07: decode("utf-8","ignore") у cp1251-сайтов (bc.by) ВЫБРАСЫВАЛ всю
    # кириллицу из сохранённых страниц → charset берём из заголовка/меты
    try:
        req = urllib.request.Request(url, headers=UA)
        resp = urllib.request.urlopen(req)
        raw = resp.read()
        enc = resp.headers.get_content_charset()
        if not enc:
            m = re.search(rb'charset=["\']?([\w-]+)', raw[:4096])
            enc = m.group(1).decode("ascii", "ignore") if m else "utf-8"
        try:
            return raw.decode(enc, "replace")
        except LookupError:
            return raw.decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001
        print(f"  ⛔ {type(e).__name__}: {url[:70]}")
        return ""


def norm(url: str) -> str:
    # единый ключ дедупа (без схемы/www — http и https НЕ разные страницы)
    return re.sub(r"^https?://(www\.)?", "", url.split("#")[0]).rstrip("/")


def slug(url: str) -> str:
    s = re.sub(r"https?://[^/]+", "", url).strip("/") or "index"
    return re.sub(r"[^a-zA-Z0-9а-яА-Я._-]+", "_", s)[:120]


def crawl(name: str, starts: list) -> list:
    base_host = urllib.parse.urlparse(starts[0]).netloc.replace("www.", "")
    outdir = OUT / name
    outdir.mkdir(parents=True, exist_ok=True)
    seen, queue, report = set(), [(u, 0) for u in starts], []
    pages = 0
    while queue and pages < MAX_PAGES:
        url, depth = queue.pop(0)
        key = norm(url)
        if key in seen:
            continue
        seen.add(key)
        html = fetch(url)
        if not html:
            report.append(f"⛔ {url}")
            continue
        pages += 1
        f = outdir / f"{slug(url)}.html"
        f.write_text(html, encoding="utf-8")
        nre, npr = len(RE_WORDS.findall(html)), len(PRICE.findall(html))
        line = f"✅ d{depth} {len(html)//1024:>4}К re:{nre:>3} price:{npr:>3}  {url}"
        print(line)
        report.append(line)
        if depth >= MAX_DEPTH:
            continue
        for href in set(re.findall(r'href="([^"#]{3,150})"', html)):
            absu = urllib.parse.urljoin(url, href)
            p = urllib.parse.urlparse(absu)
            if p.netloc.replace("www.", "") != base_host:
                continue
            if not FOLLOW.search(absu):
                continue
            if re.search(r"(?i)\.(pdf|jpg|png|zip|doc)|strahovan|kredit|vklad", absu):
                continue
            if norm(absu) not in seen:
                queue.append((absu, depth + 1))
        time.sleep(1.0)
    return report


def main():
    # аргументы = какие банки гнать (пусто = все): ./bin/python bank_geo_probe2.py bc
    picked = {n: TARGETS[n] for n in sys.argv[1:]} if len(sys.argv) > 1 else TARGETS
    OUT.mkdir(exist_ok=True)
    all_report = []
    for name, starts in picked.items():
        print(f"\n===== {name} =====")
        all_report.append(f"===== {name} =====")
        all_report += crawl(name, starts)
    (OUT / "_report.txt").write_text("\n".join(all_report) + "\n", encoding="utf-8")
    print(f"\nГотово: {OUT}/ — включай VPN и возвращайся к Claude.")


if __name__ == "__main__":
    main()

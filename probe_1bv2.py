"""probe_1bv2 — целевой зонд-краулер источников «недвижимость за 1 базовую величину».

⚠ ЗАПУСКАТЬ БЕЗ VPN (белорусский IP): госсайты блокируют иностранные IP.
Порядок: VPN OFF → ./bin/python probe_1bv2.py → VPN ON → вернуться к Claude.

Что нового против probe_1bv (20.06): тот качал по ОДНОЙ странице — этот ходит вглубь
по целевым правилам каждого источника (разведка по дампам 20.06 уже сделана):
  ngi     — ngi.gki.gov.by: проверка «ожил ли» (20.06 был 403 на техобслуживании для всех)
  brest   — листинг 14 стр. + статьи-извещения по районам (в них таблицы объектов)
  gomel   — GET /realty/?price_base=on — серверный фильтр «цена = 1 БВ» (bitrix, PAGEN)
  minobl  — раздел /ru/nedvizhimoe-imushchestvo (Joomla K2, itemlist/item)
  mogilev — категория «неиспользуемые объекты» + «единая база продажи/аренды»
  vitebsk — fondgosim.vitebsk.by мёртв в DNS → ищем раздел от vitebsk-region.gov.by
Дампы → probe_1bv2/{источник}/, сводка → probe_1bv2/_report.txt.
"""
import json
import re
import socket
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "probe_1bv2"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "ru-RU,ru,be"}
socket.setdefaulttimeout(25)
_CTX = ssl.create_default_context()          # у ngi.gki битый сертификат — не падать
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

RE_WORDS = re.compile(r"(?i)здание|помещение|склад|офис|недвижим|изолирован|капитальн")
PRICE = re.compile(r"(?i)\d[\d\s\xa0’'.,]{2,}\s*(?:руб|BYN|бел)")
BV = re.compile(r"(?i)базов\w*\s*величин")

# per-источник: стартовые URL, по каким ссылкам идти вглубь, лимит страниц
TARGETS = {
    "ngi": dict(
        starts=["https://ngi.gki.gov.by/ru/", "https://ngi.gki.gov.by/ru/registry"],
        follow=r"(?i)registry|object|card|view|page=", max_pages=15),
    "brest": dict(
        starts=["https://brest-region.gov.by/ru/negosudarstvennoe-imushchestvo-305-ru/"],
        follow=r"(?i)negosudarstvennoe-imushchestvo-305-ru/page/|neispolzuem|bazovoj",
        max_pages=50),
    "gomel": dict(
        starts=["https://gomeloblim.gov.by/realty/?price_base=on",
                "https://gomeloblim.gov.by/realty/"],
        follow=r"(?i)/realty/", max_pages=30),
    "minobl": dict(
        starts=["https://minoblim.by/ru/nedvizhimoe-imushchestvo"],
        follow=r"(?i)nedvizhimoe-imushchestvo|itemlist|/item/|start=", max_pages=40),
    "mogilev": dict(
        starts=["https://mogilev-region.gov.by/investicionnyy-potencial-oblasti/neispolzuemye-obekty-nedvizhimosti",
                "https://mogilev-region.gov.by/gosudarstvennoe-imushchestvo/edinyy-reestr-imushchestva-edinaya-baza-prodazhiarendy-imushchestva"],
        follow=r"(?i)neispolzuem|imushchestv|page=|/page/", max_pages=30),
    "vitebsk": dict(
        starts=["https://vitebsk-region.gov.by/"],
        follow=r"(?i)imushchestv|neispolzuem|nedvizhim|bazov", max_pages=20),
}
MAX_DEPTH = 3
SKIP = re.compile(r"(?i)\.(pdf|jpg|jpeg|png|gif|zip|docx?|xlsx?)($|\?)|/news/|feed|login|mailto")


def ip_country():
    try:
        with urllib.request.urlopen(
                "http://ip-api.com/json/?fields=country,countryCode,query", timeout=10) as h:
            d = json.load(h)
        return d.get("countryCode"), d.get("country", "?"), d.get("query", "?")
    except Exception:  # noqa: BLE001
        return None, None, None


def fetch(url: str) -> str:
    # charset из заголовка/меты (урок bc.by: decode utf-8/ignore выбрасывал кириллицу cp1251)
    try:
        req = urllib.request.Request(url, headers=UA)
        resp = urllib.request.urlopen(req, context=_CTX)
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
        print(f"  ⛔ {type(e).__name__}: {str(e)[:50]} {url[:70]}")
        return ""


def norm(url: str) -> str:
    # ключ дедупа: без схемы/www, query СОХРАНЯЕМ (у gomel/K2 всё в query)
    return re.sub(r"^https?://(www\.)?", "", url.split("#")[0]).rstrip("/")


def slug(url: str) -> str:
    s = re.sub(r"https?://[^/]+", "", url).strip("/") or "index"
    return re.sub(r"[^a-zA-Z0-9а-яА-Я._-]+", "_", s)[:120]


def crawl(name: str, cfg: dict) -> list:
    follow = re.compile(cfg["follow"])
    base_host = urllib.parse.urlparse(cfg["starts"][0]).netloc.replace("www.", "")
    outdir = OUT / name
    outdir.mkdir(parents=True, exist_ok=True)
    seen, queue, report, pages = set(), [(u, 0) for u in cfg["starts"]], [], 0
    while queue and pages < cfg["max_pages"]:
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
        (outdir / f"{slug(url)}.html").write_text(html, encoding="utf-8")
        line = (f"✅ d{depth} {len(html)//1024:>4}К re:{len(RE_WORDS.findall(html)):>3} "
                f"price:{len(PRICE.findall(html)):>3} 1БВ:{len(BV.findall(html)):>2}  {url}")
        print(line)
        report.append(line)
        if depth >= MAX_DEPTH:
            continue
        for href in set(re.findall(r'href="([^"#]{3,200})"', html)):
            absu = urllib.parse.urljoin(url, href)
            if urllib.parse.urlparse(absu).netloc.replace("www.", "") != base_host:
                continue
            if SKIP.search(absu) or not follow.search(absu):
                continue
            if norm(absu) not in seen:
                queue.append((absu, depth + 1))
        time.sleep(1.0)
    return report


def main():
    cc, country, ip = ip_country()
    print(f"IP: {country} ({ip})")
    if cc and cc != "BY":
        print(f"⚠ IP не белорусский ({cc}) — госсайты отдадут 403/таймаут. "
              f"Выключите VPN и запустите снова.\n")
    picked = {n: TARGETS[n] for n in sys.argv[1:]} if len(sys.argv) > 1 else TARGETS
    OUT.mkdir(exist_ok=True)
    all_report = [f"IP: {country} ({ip})"]
    for name, cfg in picked.items():
        print(f"\n===== {name} =====")
        all_report.append(f"===== {name} =====")
        all_report += crawl(name, cfg)
    (OUT / "_report.txt").write_text("\n".join(all_report) + "\n", encoding="utf-8")
    print(f"\n📁 Готово: {OUT}/ — включайте VPN и возвращайтесь к Claude "
          "(скажите «готово», я прочитаю probe_1bv2/_report.txt).")


if __name__ == "__main__":
    main()

"""research_probe — зонд болей собственников коммерческой недвижимости (customer research).

⚠ ЗАПУСКАТЬ БЕЗ VPN (белорусский IP): белорусские форумы (onliner/realt) под иностранным
IP отдают капчу/гео-блок, а из-под бел. IP — чистый серверный HTML с реальными репликами
людей. Зонд ходит BFS по форумным веткам/статьям, сохраняет каждую страницу (HTML + чистый
текст) в research_probe_out/{источник}/ и в _report.txt ранжирует страницы по числу
«болевых слов» (риелтор/комиссия/не могу продать/висит/арендатор…). По «жирным» страницам
Claude вытащит живые цитаты собственников и заострит скрипт обзвона.

Форумы (forum.onliner.by и т.п.) — классический серверный HTML, посты видны urllib.
⚠ Комментарии под НОВОСТЯМИ бывают за JS — их зонд может не увидеть (это ок, форумы важнее).

Запуск (Денис, VPN OFF):
    ./bin/python research_probe.py               # все источники
    ./bin/python research_probe.py onliner_forum # только один
    ./bin/python research_probe.py URL1 URL2     # свои ссылки (напр. конкретную ветку)
    ./bin/python research_probe.py --selftest     # самопроверка логики
Потом VPN ON и вернуться к Claude с папкой research_probe_out/.
"""
import re
import socket
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "research_probe_out"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
      "Accept-Language": "ru,be;q=0.8"}
socket.setdefaulttimeout(20)

# По каким ссылкам идти вглубь: форумные ветки/разделы, новости, аналитика, доски.
FOLLOW = re.compile(r"(?i)viewtopic|viewforum|/forum|/news|/analitik|/wiki|/blog|/board|"
                    r"topic|/kommerch|nedvizh|arenda|prodazh|start=\d|page=\d|PAGEN|"
                    r"[?&]f=\d+|[?&]t=\d+")
# «Болевые слова» — метрика содержательности (что нам и нужно услышать от собственника).
PAIN = re.compile(r"(?i)риелтор|риэлтор|\bагент|комисси|продать|продаю|сдать|сдаю|аренд|"
                  r"арендатор|покупател|висит|простаива|надоел|достал|обман|мошенник|"
                  r"звонят|навязыва|торг|собственник|не могу продать|без посредник")

# v2 (после разведки 11.07): бьём ПРЯМО в ветки-обсуждения, где собственники/клиенты
# изливают боль, а не в разделы-списки и не в листинги (там pain-слова механические).
TARGETS = {
    # Onliner — раздел обсуждений недвижимости (f=138) + «жалобная книга» + живые ветки с портала.
    # Зонд спустится в темы (viewtopic) и пройдёт их пагинацию (start=).
    "onliner_disc": ["https://forum.onliner.by/viewforum.php?f=138",
                     "https://forum.onliner.by/viewtopic.php?t=2928186",   # жалобная книга недвижимости
                     "https://forum.onliner.by/viewtopic.php?t=24798149",
                     "https://forum.onliner.by/viewtopic.php?t=25607220",
                     "https://forum.onliner.by/viewtopic.php?t=25619049"],
    # Realt — редакционные обзоры рынка (вторичный источник: экспертная рамка, не «крик души»)
    "realt_news": ["https://realt.by/news/category/kommercheskaja-nedvizhimost/",
                   "https://realt.by/news/article/47404/"],
}
MAX_PAGES = 80
MAX_DEPTH = 3
SKIP = re.compile(r"(?i)\.(pdf|jpe?g|png|gif|zip|docx?|xlsx?|css|js)(\?|$)|"
                  r"login|register|logout|reply|posting|/user|/profile|cart|payment|"
                  r"whatsapp|viber|t\.me|facebook|instagram|youtube")


def fetch(url: str) -> str:
    # charset из заголовка/меты (грабля bc.by: decode utf-8 у cp1251 выбрасывает кириллицу)
    try:
        resp = urllib.request.urlopen(urllib.request.Request(url, headers=UA))
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


def norm(url: str) -> str:  # единый ключ дедупа: http==https, без www/якоря/хвостового /
    return re.sub(r"^https?://(www\.)?", "", url.split("#")[0]).rstrip("/")


def slug(url: str) -> str:
    s = re.sub(r"https?://[^/]+", "", url).strip("/") or "index"
    return re.sub(r"[^a-zA-Z0-9а-яА-Я._=-]+", "_", s)[:120]


def to_text(html: str) -> str:  # грубая чистка тегов — чтобы читать реплики без разметки
    html = re.sub(r"(?is)<(script|style|head).*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>", "\n", html)
    text = re.sub(r"(?s)<[^>]+>", " ", html)
    text = (text.replace("&nbsp;", " ").replace("&quot;", '"')
                .replace("&laquo;", "«").replace("&raquo;", "»").replace("&amp;", "&"))
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"\n{3,}", "\n\n", text)).strip()


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
            report.append((0, f"⛔ {url}"))
            continue
        pages += 1
        text = to_text(html)
        (outdir / f"{slug(url)}.html").write_text(html, encoding="utf-8")
        (outdir / f"{slug(url)}.txt").write_text(text, encoding="utf-8")
        npain = len(PAIN.findall(text))
        line = f"pain:{npain:>4} d{depth} {len(html)//1024:>4}К  {url}"
        print(("🔥 " if npain >= 15 else "   ") + line)
        report.append((npain, line))
        if depth >= MAX_DEPTH:
            continue
        for href in set(re.findall(r'href="([^"#]{3,180})"', html)):
            absu = urllib.parse.urljoin(url, href)
            if urllib.parse.urlparse(absu).netloc.replace("www.", "") != base_host:
                continue
            if SKIP.search(absu) or not FOLLOW.search(absu):
                continue
            if norm(absu) not in seen:
                queue.append((absu, depth + 1))
        time.sleep(1.0)
    return report


def selftest():
    assert norm("https://www.x.by/a/") == norm("http://x.by/a") == "x.by/a"
    demo = "Риелторы достали звонками, не могу продать, объект висит, комиссию жалко."
    assert len(PAIN.findall(demo)) >= 4, PAIN.findall(demo)
    assert "«текст»" in to_text("<p>&laquo;текст&raquo;</p>")
    assert FOLLOW.search("viewtopic.php?f=1&t=99") and not FOLLOW.search("/logout")
    print("selftest OK (norm/PAIN/to_text/FOLLOW)")


def main():
    args = sys.argv[1:]
    if args == ["--selftest"]:
        return selftest()
    OUT.mkdir(exist_ok=True)
    urls = [a for a in args if a.startswith("http")]
    picked = ({"custom": urls} if urls else
              {n: TARGETS[n] for n in args if n in TARGETS} or TARGETS)
    report = []
    for name, starts in picked.items():
        print(f"\n===== {name} =====")
        report.append(f"\n===== {name} =====")
        rows = crawl(name, starts)
        report += [ln for _, ln in rows]
        top = sorted((r for r in rows if isinstance(r[0], int)), reverse=True)[:10]
        report.append(f"--- ТОП по болевым словам ({name}) ---")
        report += ["  " + ln for _, ln in top]
    (OUT / "_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"\nГотово: {OUT}/  (жирные = 🔥). Включай VPN и возвращайся к Claude.")


if __name__ == "__main__":
    main()

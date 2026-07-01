#!/usr/bin/env python3
"""Автономный разведзонд гео-заблокированных сайтов — ЗАПУСКАТЬ БЕЗ VPN (белорусский IP).

ЗАЧЕМ: domovita.by и edc.sale под иностранным IP (VPN/Psiphon) недоступны —
domovita отдаёт nginx 423, edc.sale дропает TCP (timeout). Это гео-блок (как gki/
gostorg/elot): сайты пускают только из РБ/РФ. Claude сидит под VPN и проверить их
сам не может, поэтому зонд автономный: ты запускаешь его БЕЗ VPN, он скачивает
страницы коммерции на диск, а ты приносишь результат Claude — по нему Claude
напишет парсеры (как уже сделал для gohome.by и byrealty.by).

КАК ЗАПУСТИТЬ (просто, по шагам):
  1. Выключи VPN / Psiphon (нужен белорусский IP).
  2. В терминале:  python3 geo_probe.py
     (зависимостей нет — только стандартный Python, venv не нужен)
  3. Включи VPN обратно и скажи Claude «зонд готов».
     Рядом появятся: папка geo_probe_out/ (HTML страниц) + geo_probe_report.txt (сводка).

Скрипт ничего не ломает: только читает страницы и сохраняет их на диск.
"""
import re
import urllib.error
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "geo_probe_out"
REPORT = Path(__file__).parent / "geo_probe_report.txt"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Upgrade-Insecure-Requests": "1",
}

SITES = {
    "domovita.by": {
        "base": "https://domovita.by",
        "seeds": [f"/minsk/{cat}/{deal}"
                  for cat in ("office", "warehouses", "shopping", "service")
                  for deal in ("sale", "rent")],
        "link": r"(?:commercial|kommerch|arenda|prodazha)",
        # ссылка деталки объявления (длиннее категории, с slug/id)
        "detail": r'href="(https://domovita\.by/[a-z-]+/(?:office|warehouses|shopping|service)/(?:sale|rent)/[^"]+)"',
    },
    "edc.sale": {
        "base": "https://edc.sale",
        "seeds": ["/ru/by/real-estate/commercial/sale",
                  "/ru/by/real-estate/commercial/rent"],
        "link": r"(?:commercial|real-estate|arenda|prodazha|/sale|/rent)",
        "detail": r'href="(https://edc\.sale/ru/[^"]+/real-estate/commercial/[^"]+\.html)"',
    },
}


def get(url: str):
    try:
        req = urllib.request.Request(url, headers={**HEADERS, "Referer": url.rsplit("/", 1)[0]})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def signals(html: str) -> str:
    out = []
    for pat, lbl in [(r"__NEXT_DATA__", "Next.js"), (r"window\.__NUXT__", "Nuxt/SPA"),
                     (r"application/ld\+json", "ld+json"),
                     (r'data-object-id|data-id="|data-offer', "data-id карточки"),
                     (r"/\d{5,}", "числовые id в ссылках")]:
        if re.search(pat, html):
            out.append(lbl)
    return ", ".join(out) or "—"


def probe_site(name: str, cfg: dict, lines: list) -> None:
    base, sdir = cfg["base"], OUT / name.replace(".", "_")
    sdir.mkdir(parents=True, exist_ok=True)
    hdr = f"\n========== {name} =========="
    print(hdr); lines.append(hdr)

    # главная → автопоиск реальных ссылок коммерции
    extra = []
    _, home = get(base + "/")
    if isinstance(home, str) and len(home) > 1000:
        found = re.findall(r'href="(/[^"]*' + cfg["link"] + r'[^"]*)"', home)
        extra = list(dict.fromkeys(found))[:8]

    seen, any_ok, detail_urls = set(), False, []
    for path in cfg["seeds"] + extra:
        url = base + path
        if url in seen:
            continue
        seen.add(url)
        code, body = get(url)
        if isinstance(body, str) and code == 200 and len(body) > 1000:
            any_ok = True
            fn = sdir / ((re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_") or "home") + ".html")
            fn.write_text(body, encoding="utf-8")
            ids = len(set(re.findall(r"/(\d{5,})", body)))
            if cfg.get("detail"):
                detail_urls += re.findall(cfg["detail"], body)
            msg = f"  [200] {path}\n        {len(body)} симв | {signals(body)} | id ~{ids} → {fn.relative_to(OUT.parent)}"
        else:
            short = body if isinstance(body, str) and len(body) < 120 else "пусто/блок"
            msg = f"  [{code}] {path}  {short}"
        print(msg); lines.append(msg)

    # 1 деталка объявления — чтобы Claude увидел, где телефон
    for durl in dict.fromkeys(detail_urls):
        code, body = get(durl)
        if isinstance(body, str) and code == 200 and len(body) > 1000:
            (sdir / "detail_sample.html").write_text(body, encoding="utf-8")
            tel = re.search(r"\+?375[\s()\-]?\d{2}[\s()\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}", body)
            msg = f"  [деталь] {durl}\n        телефон в HTML: {tel.group(0) if tel else 'НЕ найден (за кликом?)'} → {name.replace('.', '_')}/detail_sample.html"
            print(msg); lines.append(msg)
            break

    if not any_ok:
        warn = f"  ⚠ {name}: ни одной 200-страницы. Если VPN ВЫКЛЮЧЕН и всё равно блок —\n    значит дело не только в гео; сообщи Claude (попробуем браузерный обход)."
        print(warn); lines.append(warn)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    lines = ["=== РАЗВЕДЗОНД гео-заблокированных сайтов ===",
             "ВАЖНО: запускать БЕЗ VPN (белорусский IP)."]
    print(lines[0]); print(lines[1])
    for name, cfg in SITES.items():
        probe_site(name, cfg, lines)
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ Готово. Папка: {OUT}\n   Отчёт: {REPORT}")
    print("   Включи VPN и скажи Claude «зонд готов» — он разберёт результат и напишет парсеры.")


if __name__ == "__main__":
    main()

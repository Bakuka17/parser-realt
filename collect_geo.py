"""collect_geo — сбор ГЕО-ЗАБЛОКИРОВАННЫХ источников (domovita.by + edc.sale) в общий файл.

⚠⚠ ЗАПУСКАТЬ БЕЗ VPN / Psiphon (нужен БЕЛОРУССКИЙ IP)! ⚠⚠
Под VPN: domovita отдаёт 423, edc — timeout → соберётся 0. Скрипт проверяет страну IP
и предупреждает. Это отдельный оркестратор (не входит в collect_realty.py, который гоняется
под VPN), как kufar_phones — собирается руками с белорусского IP.

Пишет в commercial_realty.xlsx: читает существующую базу, ДОПИСЫВАЕТ новое (дедуп по URL,
домены разные — не пересекаются), в конце восстанавливает вкладку «Аукционы».

Запуск (VPN ВЫКЛЮЧЕН):
  ./bin/python collect_geo.py                 # domovita + edc → дописать в базу
  ./bin/python collect_geo.py --sources domovita
  ./bin/python collect_geo.py --max-pages 5   # ограничить глубину (тест)
  ./bin/python collect_geo.py --no-details    # domovita без телефонов (быстро)
"""
from __future__ import annotations

import argparse
import json
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import realty_parser_v8 as R
import domovita_parser as D
import edc_parser as E

HERE = Path(__file__).parent
DEFAULT_OUT = HERE / "commercial_realty.xlsx"
ALL = ["domovita", "edc"]


def exit_country() -> str | None:
    try:
        with urllib.request.urlopen(
            "http://ip-api.com/json/?fields=countryCode", timeout=10) as h:
            return json.load(h).get("countryCode")
    except Exception:  # noqa: BLE001
        return None


def run_domovita(prev_urls, cfg) -> list[dict]:
    new: list[dict] = []
    scfg = SimpleNamespace(max_pages=cfg.max_pages, full=cfg.full, no_details=cfg.no_details)
    for city in D.CITIES:
        for cat, type_ in D.CATS:
            for dp, deal in D.DEAL_PATHS:
                items = D.scrape_category(city, cat, type_, dp, deal, prev_urls, scfg)
                new.extend(it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls)
    return new


def run_edc(prev_urls, cfg) -> list[dict]:
    new: list[dict] = []
    scfg = SimpleNamespace(max_pages=cfg.max_pages, full=cfg.full)
    for dp, deal in E.CATEGORIES:
        items = E.scrape_category(dp, deal, prev_urls, scfg)
        new.extend(it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls)
    return new


RUNNERS = {"domovita": run_domovita, "edc": run_edc}


def main() -> None:
    p = argparse.ArgumentParser(description="Сбор гео-заблокированных (domovita+edc). БЕЗ VPN!")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--sources", default=",".join(ALL))
    p.add_argument("--max-pages", type=int, default=100)
    p.add_argument("--full", action="store_true")
    p.add_argument("--no-details", action="store_true", help="domovita без телефонов")
    cfg = p.parse_args()
    cfg.out = cfg.out.expanduser().resolve()
    sources = [s.strip() for s in cfg.sources.split(",") if s.strip() in RUNNERS]

    cc = exit_country()
    print(f"🌍 IP-страна: {cc or '?'}" + ("" if cc == "BY" else "  ⚠⚠ НЕ Беларусь!"))
    if cc != "BY":
        print("   ⚠ domovita/edc гео-блокированы — выключи VPN/Psiphon, иначе соберётся 0.\n"
              "   Продолжаю (вдруг IP уже сменился)…")

    prev_db, _ = R.load_prev_db(cfg.out)
    prev_urls = set() if cfg.full else set(prev_db.keys())
    snapshot: dict = {}
    for _u, _r in prev_db.items():
        d, hsh = _r.get("_deal"), _r.get("Хэш")
        if d and hsh:
            snapshot.setdefault(d, set()).add(str(hsh))

    print(f"🚀 collect_geo | источники: {', '.join(sources)} | БД {len(prev_db)} | out={cfg.out}")
    all_new: list[dict] = []
    summary: dict[str, str] = {}
    for src in sources:
        print(f"\n{'='*50}\n=== {src} ===\n{'='*50}")
        try:
            got = RUNNERS[src](prev_urls, cfg)
            all_new.extend(got)
            summary[src] = f"{len(got)} новых"
            for it in got:
                prev_urls.add(R.normalize_url(it["Ссылка"]))
            R.write_excel(list(prev_db.values()) + all_new, cfg.out, prev_hashes=snapshot)
            print(f"  💾 чекпойнт после {src}: всего новых {len(all_new)}")
        except Exception as e:  # noqa: BLE001
            summary[src] = f"✖ {type(e).__name__}: {e}"
            print(f"  ✖ {src} упал: {e}")

    final = list(prev_db.values()) + all_new
    R.write_excel(final, cfg.out, prev_hashes=snapshot)
    try:
        import embed_auctions
        embed_auctions.embed(main=cfg.out)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ вкладка «Аукционы» не встроена: {e}")
    print(f"\n📦 ИТОГ: {len(final)} (новых: {len(all_new)}, из БД: {len(prev_db)})")
    for src in sources:
        print(f"   {src}: {summary.get(src, '—')}")


if __name__ == "__main__":
    main()

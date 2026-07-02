"""collect_realty — единая точка входа: realt.by + megapolis + kufar → один Excel.

Одна общая БД (commercial_realty.xlsx). Дедуп по URL работает для всех источников
(домены разные — URL не пересекаются). Источники запускаются по очереди и
ИЗОЛИРОВАННО: бан/сбой одного не роняет остальные. Колонка «Источник» уже
проставляется каждым парсером. Чекпойнт после каждого источника + жёлтая
подсветка новых строк.

Запуск:
  ./bin/python collect_realty.py                       # все источники, инкрементально
  ./bin/python collect_realty.py --sources megapolis,kufar
  ./bin/python collect_realty.py --city belarus        # kufar по всей РБ
  ./bin/python collect_realty.py --max-pages 5         # ограничить глубину (тест)
  ./bin/python collect_realty.py --full                # полный перепрогон
  ./bin/python collect_realty.py --no-realt-details    # realt без захода в карточки
"""
from __future__ import annotations

import argparse
import asyncio
import re
import shutil
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import realty_parser_v8 as R
import megapolis_parser as M
import kufar_parser as K
import gohome_parser as G
import byrealty_parser as BY
import price_history as PH

HERE = Path(__file__).parent
DEFAULT_OUT = HERE / "commercial_realty.xlsx"
ALL_SOURCES = ["realt", "megapolis", "kufar", "gohome", "byrealty"]
# Цель облачного бэкапа: Яндекс.Диск (предпочтение пользователя).
# Папка ~/Yandex.Disk.localized/ — это и есть Яндекс.Диск (Finder показывает её как «Яндекс.Диск»).
BACKUP_DIR = Path.home() / "Yandex.Disk.localized" / "realty_backup"


def update_memory_and_backup(out_file: Path) -> None:
    """Обновляет авто-блок состояния в CLAUDE.md и копирует код+данные+память в iCloud."""
    # 1. Свежая статистика из итогового файла
    try:
        db, _ = R.load_prev_db(out_file)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ память: не смог прочитать {out_file.name}: {e}")
        db = {}
    src = Counter()
    ph = 0
    for it in db.values():
        src[it.get("Источник", "?")] += 1
        if it.get("Телефон") not in (None, "", "н/у"):
            ph += 1
    total = len(db)
    ph_pct = (100 * ph // total) if total else 0

    # 2. Переписать авто-блок в CLAUDE.md (мой ручной текст не трогаем)
    claude_md = HERE / "CLAUDE.md"
    if claude_md.exists():
        lines = [f"`{out_file.name}` = **{total} объектов** (обновлено {date.today():%d.%m.%Y}):"]
        for s, c in src.most_common():
            lines.append(f"- {s}: {c}")
        lines.append(f"Телефоны: ~{ph_pct}%.")
        block = (
            "<!-- AUTO-STATE-START (обновляется автоматически в конце collect_realty.py) -->\n"
            + "\n".join(lines)
            + "\n<!-- AUTO-STATE-END -->"
        )
        text = claude_md.read_text(encoding="utf-8")
        new_text = re.sub(
            r"<!-- AUTO-STATE-START.*?<!-- AUTO-STATE-END -->",
            block.replace("\\", "\\\\"),
            text,
            flags=re.S,
        )
        if new_text != text:
            claude_md.write_text(new_text, encoding="utf-8")
            print("  🧠 CLAUDE.md: состояние обновлено")

    # 3. Бэкап в Яндекс.Диск (всё: код + xlsx + saved_realty + photos/ + CLAUDE.md + .command).
    if BACKUP_DIR.parent.exists():
        try:
            BACKUP_DIR.mkdir(exist_ok=True)
            n = 0
            for f in (list(HERE.glob("*.py")) + list(HERE.glob("*.xlsx"))
                      + list(HERE.glob("*.command")) + list(HERE.glob("*.json"))):  # json: история цен и пр.
                if f.name.startswith("~$"):
                    continue
                shutil.copy2(f, BACKUP_DIR / f.name)
                n += 1
            if claude_md.exists():
                shutil.copy2(claude_md, BACKUP_DIR / "CLAUDE.md")
            # photos/ (фото избранных) — синкаем целиком
            photos_src = HERE / "photos"
            if photos_src.is_dir():
                shutil.copytree(photos_src, BACKUP_DIR / "photos", dirs_exist_ok=True)
            with (BACKUP_DIR / "BACKUP_INFO.txt").open("a", encoding="utf-8") as fh:
                fh.write(f"{date.today():%Y-%m-%d} collect_realty: {total} объектов, тел {ph_pct}%\n")
            print(f"  ☁️ Яндекс.Диск: бэкап обновлён ({n} файлов + CLAUDE.md + photos/)")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ бэкап в Яндекс.Диск не удался: {e}")
    else:
        print("  (Яндекс.Диск не найден — бэкап пропущен)")


# Примечание: DATE_STOP в оркестраторе НЕ используем (last_run=None).
# Причина: общий файл имеет ОДНУ дату последнего прогона, а каждый источник
# собран до своего момента. Если у источника свежей даты нет в файле (первый
# сбор), DATE_STOP по чужой дате остановит пагинацию слишком рано. Поэтому
# полагаемся на ALL_KNOWN (дедуп по URL) — он корректен для каждого источника.

def collect_realt(prev_urls, last_run, cfg, on_checkpoint=None) -> list[dict]:
    rcfg = R.RunConfig(
        limit_per_category=10_000,
        fetch_details=not cfg.no_realt_details,
        headless=not cfg.headed,
        out_file=cfg.out,
        debug_file=(R.DEFAULT_DEBUG_FILE.resolve() if cfg.debug else None),
        goto_retries=3,
        verbose=False,
        max_pages=cfg.max_pages,
        full_rescan=cfg.full,
    )
    return asyncio.run(
        R.collect_new(rcfg, set() if cfg.full else prev_urls, None, on_checkpoint=on_checkpoint)
    )


def collect_megapolis(prev_urls, last_run, cfg, prices=None) -> list[dict]:
    scfg = SimpleNamespace(max_pages=cfg.max_pages, full=cfg.full)
    new: list[dict] = []
    pu = set() if cfg.full else prev_urls
    for ci, (path, deal, type_) in enumerate(M.CATEGORIES):
        items = M.scrape_category(path, deal, type_, pu, None, scfg)
        if prices is not None:
            prices.track(items, "megapolis-real.by")
        new.extend(it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls)
    return new


def collect_kufar(prev_urls, last_run, cfg, prices=None) -> list[dict]:
    scfg = SimpleNamespace(max_pages=cfg.max_pages, full=cfg.full)
    new: list[dict] = []
    pu = set() if cfg.full else prev_urls
    for deal_frag, deal in K.DEALS:
        items = K.scrape_deal(cfg.city, deal_frag, deal, pu, None, scfg)
        if prices is not None:
            prices.track(items, "kufar.by")
        new.extend(it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls)
    return new


def collect_gohome(prev_urls, last_run, cfg, prices=None) -> list[dict]:
    scfg = SimpleNamespace(max_pages=cfg.max_pages, full=cfg.full, coords=False)
    new: list[dict] = []
    pu = set() if cfg.full else prev_urls
    for deal_path, deal in G.CATEGORIES:
        items = G.scrape_category(deal_path, deal, pu, None, scfg)
        if prices is not None:
            prices.track(items, "gohome.by")
        new.extend(it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls)
    return new


def collect_byrealty(prev_urls, last_run, cfg, prices=None) -> list[dict]:
    scfg = SimpleNamespace(max_pages=1, full=cfg.full)
    new: list[dict] = []
    pu = set() if cfg.full else prev_urls
    for path, deal in BY.CATEGORIES:
        items = BY.scrape_category(path, deal, pu, None, scfg)
        if prices is not None:
            prices.track(items, "byrealty.by")
        new.extend(it for it in items if R.normalize_url(it["Ссылка"]) not in prev_urls)
    return new


COLLECTORS = {
    "realt": collect_realt,
    "megapolis": collect_megapolis,
    "kufar": collect_kufar,
    "gohome": collect_gohome,
    "byrealty": collect_byrealty,
}


def main() -> None:
    p = argparse.ArgumentParser(description="Сбор коммерческой недвижимости из всех источников в один файл.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--sources", default=",".join(ALL_SOURCES),
                   help="через запятую: realt,megapolis,kufar (по умолчанию все)")
    p.add_argument("--city", default="belarus", help="город для kufar (belarus=вся РБ, дефолт | minsk | ...)")
    p.add_argument("--max-pages", type=int, default=100)
    p.add_argument("--full", action="store_true", help="полный перепрогон всех источников")
    p.add_argument("--no-realt-details", action="store_true", help="realt без захода в карточки")
    p.add_argument("--headed", action="store_true", help="realt с окном браузера")
    p.add_argument("--debug", action="store_true", help="realt: писать debug_cards.txt")
    cfg = p.parse_args()
    cfg.out = cfg.out.expanduser().resolve()

    sources = [s.strip() for s in cfg.sources.split(",") if s.strip() in COLLECTORS]
    if not sources:
        print("Нет валидных источников. Доступны:", ", ".join(ALL_SOURCES))
        return

    # Общая БД
    prev_db, last_run = R.load_prev_db(cfg.out)
    prev_urls = set() if cfg.full else set(prev_db.keys())
    snapshot: dict = {}
    for _u, _r in prev_db.items():
        d, h = _r.get("_deal"), _r.get("Хэш")
        if d and h:
            snapshot.setdefault(d, set()).add(str(h))

    print(f"🚀 collect_realty. Дата: {date.today():%d.%m.%Y}")
    print(f"   источники: {', '.join(sources)} | город(kufar): {cfg.city}")
    print(f"   режим: {'ПОЛНЫЙ' if cfg.full else 'инкрементальный'} | БД: {len(prev_db)} | out: {cfg.out}")
    if last_run and not cfg.full:
        print(f"   последний прогон: {last_run:%d.%m.%Y}")

    all_new: list[dict] = []
    summary: dict[str, str] = {}
    prices = PH.Tracker(prev_db, R.normalize_url)  # история цен: known-URL сравниваются с базой
    for src in sources:
        print(f"\n{'='*60}\n=== ИСТОЧНИК: {src} ===\n{'='*60}")
        try:
            if src == "realt":
                _base = [] if cfg.full else list(prev_db.values())
                _prior = list(all_new)  # новые из уже отработавших источников

                def _realt_ckpt(done_partial, _base=_base, _prior=_prior):
                    R.write_excel(_base + _prior + done_partial, cfg.out, prev_hashes=snapshot)

                got = collect_realt(prev_urls, last_run, cfg, on_checkpoint=_realt_ckpt)
            else:
                got = COLLECTORS[src](prev_urls, last_run, cfg, prices)
            all_new.extend(got)
            summary[src] = f"{len(got)} новых"
            # после источника — обновим prev_urls и сделаем чекпойнт
            for it in got:
                prev_urls.add(R.normalize_url(it["Ссылка"]))
            base = [] if cfg.full else list(prev_db.values())
            R.write_excel(base + all_new, cfg.out, prev_hashes=snapshot)
            print(f"  💾 чекпойнт после {src}: всего новых {len(all_new)}")
        except Exception as e:  # noqa: BLE001
            summary[src] = f"✖ ОШИБКА: {type(e).__name__}: {e}"
            print(f"  ✖ источник {src} упал: {e} — продолжаю с остальными")

    base = [] if cfg.full else list(prev_db.values())
    final = base + all_new
    R.write_excel(final, cfg.out, prev_hashes=snapshot)
    # вкладка «Аукционы» в тот же файл (realty пересоздаёт файл → восстанавливаем её здесь)
    try:
        import embed_auctions
        embed_auctions.embed(main=cfg.out)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ вкладка «Аукционы» не встроена: {e}")
    print(f"\n{'='*60}\n📦 ИТОГ: {len(final)} объектов (новых: {len(all_new)}, из БД: {len(base)})")
    for src in sources:
        print(f"   {src}: {summary.get(src, '—')}")
    print(f"   файл: {cfg.out}")
    if prices.changes:
        down = sum(1 for c in prices.changes if c["dir"] == "down")
        up = sum(1 for c in prices.changes if c["dir"] == "up")
        prices.flush()
        print(f"   💰 изменений цен: {len(prices.changes)} (↓{down} ↑{up}) → {PH.HISTORY_FILE.name}")

    # Авто-память + бэкап
    update_memory_and_backup(cfg.out)


if __name__ == "__main__":
    main()

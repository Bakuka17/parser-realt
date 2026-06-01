"""merge_sources — объединяет выгрузки нескольких источников в один Excel.

Читает realt/megapolis/kufar xlsx (одна схема колонок), складывает в общий файл
с уже проставленной колонкой «Источник». Внутри источника URL уникальны; между
источниками URL разные (разные домены), поэтому простое объединение не теряет и
не дублирует строки. Опциональный кросс-дедуп по (адрес+площадь) — флаг --dedup-cross.

Запуск:
  ./bin/python merge_sources.py
  ./bin/python merge_sources.py --dedup-cross
  ./bin/python merge_sources.py --sources commercial_realty.xlsx megapolis_realty.xlsx
"""
from __future__ import annotations

import argparse
import re
from collections import Counter
from pathlib import Path

import realty_parser_v8 as R

HERE = Path(__file__).parent
DEFAULT_SOURCES = [
    HERE / "commercial_realty.xlsx",
    HERE / "megapolis_realty.xlsx",
    HERE / "kufar_realty.xlsx",
]
DEFAULT_OUT = HERE / "all_realty.xlsx"


def cross_key(item: dict) -> str:
    """Ключ для кросс-дедупа: нормализованный адрес + площадь."""
    addr = re.sub(r"\s+", " ", (item.get("Адрес") or "").lower()).strip()
    addr = re.sub(r"[^\w\s]", "", addr)
    area = re.sub(r"[^\d.]", "", str(item.get("Площадь, м²") or ""))
    return f"{addr}|{area}"


def main() -> None:
    p = argparse.ArgumentParser(description="Слияние источников коммерческой недвижимости.")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--sources", nargs="*", type=Path, default=DEFAULT_SOURCES)
    p.add_argument(
        "--dedup-cross",
        action="store_true",
        help="убирать вероятные дубли между источниками по адрес+площадь "
        "(приоритет источника: realt.by > megapolis > kufar)",
    )
    cfg = p.parse_args()
    cfg.out = cfg.out.expanduser().resolve()

    # приоритет источника при кросс-дедупе (меньше = важнее)
    src_priority = {"realt.by": 0, "megapolis-real.by": 1, "kufar.by": 2}

    all_items: list[dict] = []
    per_source: Counter = Counter()
    for src in cfg.sources:
        src = src.expanduser().resolve()
        if not src.exists():
            print(f"  ⚠ пропуск (нет файла): {src.name}")
            continue
        db, _ = R.load_prev_db(src)
        all_items.extend(db.values())
        per_source[src.name] = len(db)
        print(f"  ✓ {src.name}: {len(db)} объектов")

    if not all_items:
        print("Нет данных для слияния.")
        return

    before = len(all_items)
    if cfg.dedup_cross:
        best: dict[str, dict] = {}
        for it in all_items:
            k = cross_key(it)
            cur = best.get(k)
            if cur is None:
                best[k] = it
            else:
                pri_new = src_priority.get(it.get("Источник", ""), 9)
                pri_old = src_priority.get(cur.get("Источник", ""), 9)
                if pri_new < pri_old:
                    best[k] = it
        all_items = list(best.values())
        print(f"\n  кросс-дедуп: {before} → {len(all_items)} (убрано {before - len(all_items)})")

    # снапшот хэшей существующего общего файла для подсветки новых
    prev_db, _ = R.load_prev_db(cfg.out)
    snapshot: dict = {}
    for _u, _r in prev_db.items():
        d, h = _r.get("_deal"), _r.get("Хэш")
        if d and h:
            snapshot.setdefault(d, set()).add(str(h))

    print(f"\n📦 Итог: {len(all_items)} объектов из {len([s for s in per_source])} источников")
    src_counts = Counter(it.get("Источник", "?") for it in all_items)
    for s, c in src_counts.most_common():
        print(f"   {s}: {c}")
    R.write_excel(all_items, cfg.out, prev_hashes=snapshot)


if __name__ == "__main__":
    main()

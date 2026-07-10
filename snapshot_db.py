#!/usr/bin/env python3
"""Дубль базы «на всякий случай»: копия commercial_realty.xlsx рядом.

Отличие от зеркала (Яндекс), которое нас подвело 09.07.2026: копия обновляется
ТОЛЬКО если основной файл здоров. Испорченный/схлопнувшийся файл НЕ затирает дубль.

Здоров = читается openpyxl И объектов не меньше, чем в дубле (с запасом SHRINK_LIMIT).

    ./bin/python snapshot_db.py            # обновить дубль, если основа жива
    ./bin/python snapshot_db.py --status   # показать, что в основе и в дубле
"""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

import realty_parser_v8 as R

HERE = Path(__file__).parent
MAIN = HERE / "commercial_realty.xlsx"
DUP = HERE / "commercial_realty_дубль.xlsx"


def count(path: Path) -> int:
    """Объектов в файле. Нечитаемый/отсутствующий → -1 (а не 0: 0 значит «пустой, но живой»)."""
    if not path.exists():
        return -1
    try:
        return sum(len(h) for h in R.load_prev_hashes(path).values())
    except Exception:
        return -1


def status() -> int:
    main_n, dup_n = count(MAIN), count(DUP)
    print(f"основа: {MAIN.name} — {main_n if main_n >= 0 else 'НЕ ЧИТАЕТСЯ'}")
    print(f"дубль:  {DUP.name} — {dup_n if dup_n >= 0 else 'нет'}")
    return 0


def update() -> int:
    """Обновить дубль. Зовётся и из collect_realty — БЕЗ разбора argv."""
    main_n, dup_n = count(MAIN), count(DUP)
    if main_n < 0:
        print(f"✖ основа не читается ({MAIN.name}) — дубль НЕ трогаю")
        return 1
    if dup_n >= 0 and main_n < dup_n * R.SHRINK_LIMIT:
        print(f"✖ основа схлопнулась: {main_n} против {dup_n} в дубле — дубль НЕ трогаю")
        print("   Если перепрогон намеренный — удалите дубль вручную и запустите снова.")
        return 1

    shutil.copy2(MAIN, DUP)
    when = datetime.now().strftime("%d.%m.%Y %H:%M")
    was = "создан" if dup_n < 0 else f"было {dup_n}"
    print(f"✔ дубль обновлён: {DUP.name} — {main_n} объектов ({was}) · {when}")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--status", action="store_true", help="только показать состояние")
    sys.exit(status() if p.parse_args().status else update())

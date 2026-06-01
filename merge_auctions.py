"""merge_auctions — собирает все auctions_{site}.xlsx в один auctions_realty.xlsx.

Дедуп по нормализованному URL (внутри площадки уникально; между площадками
один лот может повторяться — оставляем первый). Тип объекта проставит write_excel.

Запуск: ./bin/python merge_auctions.py
"""
from pathlib import Path
import auctions_common as A

HERE = Path(__file__).parent
OUT = HERE / "auctions_realty.xlsx"


def main():
    files = sorted(HERE.glob("auctions_*.xlsx"))
    files = [f for f in files if f.name != OUT.name]
    all_items = []
    seen = set()
    per_src = {}
    for f in files:
        db = A.load_prev(f)
        added = 0
        for url, rec in db.items():
            nu = A.norm_url(url)
            if nu in seen:
                continue
            seen.add(nu)
            all_items.append(rec)
            added += 1
        per_src[f.name] = added
        print(f"  {f.name}: +{added}")
    print(f"\n📦 Итого уникальных лотов: {len(all_items)}")
    from collections import Counter
    src = Counter(it.get("Источник", "?") for it in all_items)
    for s, c in src.most_common():
        print(f"   {s}: {c}")
    A.write_excel(all_items, OUT)
    print(f"   файл: {OUT}")


if __name__ == "__main__":
    main()

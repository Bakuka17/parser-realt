"""Воспроизводим аварию 09.07.2026 и проверяем, что фикс её ловит."""
import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import realty_parser_v8 as R


def item(i, deal="Продажа"):
    r = {c: "" for c in R.COLUMNS}
    r["Ссылка"] = f"https://x.by/{i}"
    r["Хэш"] = f"h{i}"
    r["_deal"] = deal
    return r


tmp = Path(tempfile.mkdtemp())
db = tmp / "base.xlsx"

# 1. Базу из 100 объектов пишем нормально.
R.write_excel([item(i) for i in range(100)], db)
prev = R.load_prev_hashes(db)
assert sum(len(v) for v in prev.values()) == 100, "база не записалась"
print("1/5 база из 100 объектов записана — ок")

# 2. Дописывание (100 -> 105) проходит.
R.write_excel([item(i) for i in range(105)], db, prev_hashes=prev)
print("2/5 инкрементальная дозапись 105 — ок")

# 3. АВАРИЯ: пишем 1828 поверх 24326 (пропорция как 09.07) -> отказ.
try:
    R.write_excel([item(i) for i in range(7)], db, prev_hashes=prev)
    raise AssertionError("защёлка НЕ сработала — база была бы затёрта")
except RuntimeError as e:
    assert "отказ записи" in str(e), e
    print("3/5 схлопывание 105 -> 7 отклонено — ок")

# 4. Намеренный перепрогон (--full) разрешён.
R.write_excel([item(i) for i in range(7)], db, prev_hashes=prev, allow_shrink=True)
print("4/5 --full (allow_shrink) разрешён — ок")

# 5. Битый файл больше НЕ читается как пустая база, а падает.
broken = tmp / "broken.xlsx"
broken.write_bytes(b"PK\x03\x04 not a real xlsx")
try:
    R.load_prev_db(broken)
    raise AssertionError("битый файл прочитан как пустая БД — авария повторится")
except RuntimeError as e:
    assert "не смог прочитать" in str(e), e
    print("5/6 битый файл -> RuntimeError, запись отменена — ок")

# 6. Процесс убит ПОСРЕДИ сохранения (закрыли программу / выключили свет).
#    До atomic_save это оставляло обрезанный zip → база не читалась.
live = tmp / "live.xlsx"
R.write_excel([item(i) for i in range(50)], live)
before = live.read_bytes()

real_replace = R.os.replace
R.os.replace = lambda *a, **k: (_ for _ in ()).throw(KeyboardInterrupt("убит посреди записи"))
try:
    R.write_excel([item(i) for i in range(60)], live, prev_hashes=R.load_prev_hashes(live))
    raise AssertionError("обрыв не сымитировался")
except KeyboardInterrupt:
    pass
finally:
    R.os.replace = real_replace

assert live.read_bytes() == before, "база испорчена обрывом записи"
assert sum(len(v) for v in R.load_prev_hashes(live).values()) == 50, "база не читается после обрыва"
print("6/6 смерть процесса посреди записи — старая база цела и читается — ок")

print("\nвсе 6 проверок пройдены")

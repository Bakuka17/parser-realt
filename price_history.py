"""История цен: лог изменений цены у уже известных объектов.

Инкрементальный сбор скачивает листинги целиком (включая известные объявления),
но раньше известные просто пропускались — снижение цены оставалось невидимым.
Теперь оркестратор сравнивает цену каждого спарсенного объявления с базой:
изменилась → запись в price_history.json + свежая цена обновляется в базе.

Сравнение — по числам с валютой (не по сырой строке), чтобы смена формата
строки цены между версиями парсеров не давала ложных «изменений».
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

HERE = Path(__file__).parent
HISTORY_FILE = HERE / "price_history.json"

_CUR_CANON = {"byn": "р", "руб": "р", "р": "р", "usd": "$", "$": "$", "€": "€", "eur": "€"}


def price_key(s: str) -> tuple:
    """«4 800 р. / 1 500 $» → (('$',1500),('р',4800)) — канон для сравнения."""
    out = []
    for m in re.finditer(r"([\d][\d\s.,]*)\s*(руб|BYN|USD|EUR|р|\$|€)", str(s or ""), re.I):
        num = re.sub(r"\D", "", m.group(1))
        if num:
            out.append((_CUR_CANON[m.group(2).lower()], int(num)))
    return tuple(sorted(set(out)))


def changed(old: str, new: str) -> bool:
    """Есть ли реальное изменение цены (не курсовой шум).

    На бел. площадках цена задаётся в одной валюте, остальные пересчитываются
    по курсу и «плывут» без участия продавца (живые данные gohome: 13 из 14
    срабатываний — курсовой шум; первичной бывает и $, и BYN — у евро-объявлений
    рубль стоял, а € плыл). Какая валюта первичная — неизвестно, поэтому правило:
    реальное изменение меняет ВСЕ валюты сразу; совпала хоть одна — шум.
    """
    o, n = dict(price_key(old)), dict(price_key(new))
    common = set(o) & set(n)
    if not common:
        return False  # форматы не пересекаются — осторожно молчим, не ложним
    return all(o[c] != n[c] for c in common)


def direction(old: str, new: str) -> str:
    """'down' / 'up' / '?' — по первой общей валюте."""
    o, n = dict(price_key(old)), dict(price_key(new))
    for cur in ("$", "р", "€"):
        if cur in o and cur in n and o[cur] != n[cur]:
            return "down" if n[cur] < o[cur] else "up"
    return "?"


def track(items: list[dict], prev_db: dict, source: str, normalize_url) -> list[dict]:
    """Сравнивает цены спарсенных items с базой prev_db (по нормализованному URL).

    Изменение → запись в результат; свежая цена мутирует запись prev_db,
    так что итоговый write_excel сохранит актуальную цену без доп. шагов.
    """
    changes: list[dict] = []
    today = f"{date.today():%d.%m.%Y}"
    for it in items:
        u = normalize_url(str(it.get("Ссылка") or ""))
        old_rec = prev_db.get(u)
        if not old_rec:
            continue
        new_p = str(it.get("Цена общая") or "").strip()
        old_p = str(old_rec.get("Цена общая") or "").strip()
        if not new_p or not old_p:
            continue
        if not changed(old_p, new_p):
            continue
        changes.append({
            "url": u,
            "hash": str(old_rec.get("Хэш") or ""),
            "deal": old_rec.get("_deal") or "",
            "source": source,
            "old": old_p,
            "new": new_p,
            "dir": direction(old_p, new_p),
            "date": today,
        })
        old_rec["Цена общая"] = new_p
        if it.get("Цена за м²"):
            old_rec["Цена за м²"] = it["Цена за м²"]
    return changes


class Tracker:
    """Накопитель изменений за прогон: один объект на весь оркестратор."""

    def __init__(self, prev_db: dict, normalize_url):
        self.prev_db, self.norm = prev_db, normalize_url
        self.changes: list[dict] = []

    def track(self, items: list[dict], source: str) -> None:
        self.changes.extend(track(items, self.prev_db, source, self.norm))

    def flush(self) -> None:
        append(self.changes)


def load() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
    return []


def append(changes: list[dict]) -> None:
    if not changes:
        return
    hist = load()
    hist.extend(changes)
    HISTORY_FILE.write_text(json.dumps(hist, ensure_ascii=False, indent=0), "utf-8")


if __name__ == "__main__":
    # self-check логики сравнения
    norm = lambda u: u.split("?")[0].rstrip("/")  # noqa: E731
    assert price_key("4 800 р. / 1 500 $") == price_key("1500 $ / 4800 руб.")
    assert price_key("120 000 $") != price_key("115 000 $")
    assert price_key("") == () and price_key("н/у") == ()
    assert direction("120 000 $", "115 000 $") == "down"
    assert direction("300 р.", "350 BYN") == "up"
    # курсовой шум: одна из валют на месте → НЕ изменение (первичная не двигалась)
    assert not changed("8 164 950,0 р. / 2 900 000 $", "8 427 980,0 р. / 2 900 000 $")
    assert not changed("254 800,0 р. / 91 000 €", "254 800,0 р. / 88 200 €")
    assert changed("1 098 045,0 р. / 390 000 $", "1 075 294,0 р. / 370 000 $")
    assert changed("300 р.", "350 р.") and not changed("300 р.", "300 руб.")
    assert changed("120 000 $", "115 000 $")  # одна валюта у обеих — сравнивается она
    db = {"https://x.by/vi/1": {"Цена общая": "120 000 $", "Хэш": "abc", "_deal": "Продажа"},
          "https://x.by/vi/2": {"Цена общая": "500 р.", "Хэш": "def", "_deal": "Аренда"}}
    items = [
        {"Ссылка": "https://x.by/vi/1?utm=1", "Цена общая": "110 000 $"},   # снижена
        {"Ссылка": "https://x.by/vi/2", "Цена общая": "500 руб."},          # тот же ценник, другой формат
        {"Ссылка": "https://x.by/vi/9", "Цена общая": "1 $"},               # новый — не наш
    ]
    ch = track(items, db, "test", norm)
    assert len(ch) == 1 and ch[0]["dir"] == "down" and ch[0]["hash"] == "abc"
    assert db["https://x.by/vi/1"]["Цена общая"] == "110 000 $"  # база обновилась
    print("self-check OK: 13/13")

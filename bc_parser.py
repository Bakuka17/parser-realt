"""bc_parser — аренда госпомещений ГХУ Управделами Президента (bc.by).

⚠ ГЕО-БЛОК → запускать БЕЗ VPN (белорусский IP), через collect_geo.py.
⚠ Сайт отдаёт windows-1251 (не utf-8!) — decode зашит.

Листинг: https://bc.by/?id=152&search=1&s_area=N (N=1..7 — области, весь список
одной страницей, пагинации нет). Таблица class=tab100p:
  - td[colspan=13] с <a ?id=152&bld=…> = заголовок ЗДАНИЯ (адрес для лотов ниже);
  - tr.row_data с 13 td = лот (или старт БЛОКА: примечание «БЛОК N кв.м», цены rowspan);
  - tr.row_data с 9 td = продолжение блока — НЕ отдельный лот (цены общие), пропускаем.
Телефоны: общий колл-центр аренды +375 17 218-18-18; для областей — кураторы
секторов со страницы ?id=149 (парсятся на лету, сбой → общий номер).
Аукционы ГХУ (?id=79) пока НЕ парсятся: HTML сохраняется в bank_geo_out2/bc/
как фикстура — парсер аукционов строится по ней следующим шагом.

Запуск standalone (без VPN): ./bin/python bc_parser.py [--fixtures]  (смоук-печать)
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

import realty_parser_v8 as R

BASE = "https://bc.by"
SOURCE = "bc.by"
MAIN_PHONE = "+375 17 218-18-18"
ORG = "ГХУ Управделами Президента"
AREAS = {1: "г. Минск", 2: "Минская область", 3: "г. Брест", 4: "г. Витебск",
         5: "г. Гомель", 6: "г. Гродно", 7: "г. Могилев"}
# ключевое слово секции ?id=149 для телефонов кураторов области (Минск = общий номер)
CURATOR_KEY = {2: "МИНСКАЯ ОБЛАСТЬ", 3: "БРЕСТСКОЙ", 4: "ВИТЕБСКОЙ",
               5: "ГОМЕЛЬСКОЙ", 6: "ГРОДНЕНСКОЙ", 7: "МОГИЛЕВСКОЙ"}
NOISE = {"САНУЗЕЛ", "ЛЕСТ.КЛЕТКА", "ТАМБУР", "КОРИДОР", "ГАРДЕРОБ", "ЛИФТ",
         "КРЫЛЬЦО", "УМЫВАЛЬНИК", "ДУШЕВАЯ", "ТУАЛЕТ"}
FIXDIR = Path(__file__).parent / "bank_geo_out2/bc"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    raw = urllib.request.urlopen(req, timeout=25).read()
    return raw.decode("cp1251", "replace")  # bc.by всегда windows-1251


def _clean_addr(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    # get_text склеивает «пр-тПартизанский» — вернуть пробел после сокращения
    return re.sub(r"^(пр-т|ул\.|пер\.|пл\.|б-р|наб\.|ш\.)(?=[А-ЯЁ])", r"\1 ", s)


def curator_phones(html_149: str) -> dict[int, tuple[str, str]]:
    """?id=149 → {s_area: (телефоны, имя первого куратора)} для областей."""
    text = BeautifulSoup(html_149, "lxml").get_text("\n", strip=True)
    out: dict[int, tuple[str, str]] = {}
    # секции идут подряд: режем текст по заголовкам-ключам
    keys = sorted(CURATOR_KEY.items(), key=lambda kv: text.find(kv[1]))
    for i, (area, key) in enumerate(keys):
        start = text.find(key)
        if start < 0:
            continue
        end = min((text.find(k2) for _, k2 in keys[i + 1:] if text.find(k2) > start),
                  default=len(text))
        seg = text[start:end]
        phones = re.findall(r"\((0\d{2,3})\)\s*\n?\s*([\d-]{7,10})", seg)
        name = re.search(r"([А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+ [А-ЯЁ][а-яё]+)", seg)
        if phones:
            joined = ", ".join(f"+375 {c.lstrip('0')} {n}" for c, n in phones[:2])
            out[area] = (joined, name.group(1) if name else "")
    return out


def parse_listing(html: str, area_n: int, phone: str, contact_name: str) -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table", class_="tab100p")
    if not table:
        return []
    items, addr = [], ""
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) == 1 and tds[0].get("colspan"):
            a = tds[0].find("a")
            if a and a.get_text(strip=True):
                addr = _clean_addr(a.get_text(" ", strip=True))
            continue
        if "row_data" not in (tr.get("class") or []) or len(tds) != 13:
            continue  # 9 td = часть блока (цены в rowspan первой строки)
        num = tds[1].get_text(strip=True)
        kind = tds[3].get_text(strip=True)
        floor = tds[4].get_text(strip=True)
        area = tds[5].get_text(strip=True).replace(",", ".")
        note = tds[10].get_text(" ", strip=True)
        per = tds[11].get_text(strip=True).replace(",", ".")
        month = tds[12].get_text(strip=True).replace(",", ".")
        if kind.upper() in NOISE and "БЛОК" not in note.upper():
            continue
        typ = kind.capitalize() or "Помещение"
        if note.upper().startswith("БЛОК"):
            typ = "Блок помещений"
            bm = re.search(r"([\d.,]+)\s*кв", note)
            if bm:
                area = bm.group(1).replace(",", ".")
        cb = tr.find("input", attrs={"name": "room_id[]"})
        room = (cb.get("value", "") if cb else "") or f"{addr}-{num}-{floor}"
        url = f"{BASE}/?id=152&search=1&s_area={area_n}&room={room}"
        h = R.hashlib.md5((R.normalize_url(url) + addr + num + area).encode()).hexdigest()[:12]
        item = {c: "н/у" for c in R.COLUMNS}
        item.update({
            "Тип": typ,
            "Адрес": f"{addr}, пом. {num}" if num else addr,
            "Район / Город": AREAS[area_n],
            "Площадь, м²": area,
            "Цена общая": f"{month} BYN/мес" if month else "",
            "Цена за м²": f"{per} BYN" if per else "",
            "Этаж / этажность": floor,
            "Описание": note if not note.upper().startswith("БЛОК") else
                        f"Сдаётся блоком ({note})",
            "Телефон": phone,
            "Контакт": ORG, "Имя контакта": contact_name,
            "Ссылка": url, "Дата публикации": "", "Источник": SOURCE,
            "Сохранить": "", "Фото URL": "", "Координаты": "",
            "Хэш": h, "_deal": "rent",
        })
        items.append(item)
    return items


def collect(prev_urls: set, use_fixtures: bool = False) -> list[dict]:
    phones: dict[int, tuple[str, str]] = {}
    try:
        h149 = (FIXDIR / "_id_149.html").read_text("utf-8") if use_fixtures \
            else fetch(f"{BASE}/?id=149")
        phones = curator_phones(h149)
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ телефоны кураторов не получены ({e}) — только общий номер")
    new: list[dict] = []
    for n in AREAS:
        try:
            if use_fixtures:
                fp = FIXDIR / f"_id_152_search_1_s_area_{n}.html"
                if not fp.exists():
                    continue
                html = fp.read_text("utf-8")
            else:
                html = fetch(f"{BASE}/?id=152&search=1&s_area={n}")
        except Exception as e:  # noqa: BLE001
            print(f"  ⛔ {AREAS[n]}: {type(e).__name__}")
            continue
        ph, nm = phones.get(n, ("", ""))
        got = parse_listing(html, n, f"{MAIN_PHONE}" + (f", {ph}" if ph else ""), nm)
        got = [it for it in got if R.normalize_url(it["Ссылка"]) not in prev_urls]
        print(f"  {AREAS[n]}: {len(got)} лотов")
        new.extend(got)
    if not use_fixtures:  # фикстура аукционов ГХУ для будущего парсера
        try:
            FIXDIR.mkdir(parents=True, exist_ok=True)
            (FIXDIR / "_id_79.html").write_text(fetch(f"{BASE}/?id=79"), encoding="utf-8")
            print("  📸 аукционы ?id=79 сохранены в bank_geo_out2/bc/ (фикстура)")
        except Exception:  # noqa: BLE001
            pass
    return new


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", action="store_true", help="HTML из bank_geo_out2/bc (без сети)")
    cfg = ap.parse_args()
    items = collect(set(), use_fixtures=cfg.fixtures)
    print(f"Всего: {len(items)}")
    for it in items[:5]:
        print(" ", it["Тип"], "|", it["Адрес"], "|", it["Площадь, м²"], "м² |",
              it["Цена общая"], "|", it["Телефон"][:60])
    filled = lambda k: sum(1 for i in items if i[k] and i[k] != "н/у")  # noqa: E731
    for k in ("Цена общая", "Площадь, м²", "Телефон", "Адрес"):
        print(f"  {k}: {filled(k)}/{len(items)}")


if __name__ == "__main__":
    main()

"""belarusbank_bank — недвижимость клиентов Беларусбанка (каталог client-property/nedvizhimost).

⚠ ГЕО-БЛОК: сайт отвечает только белорусскому IP (под VPN — SSL-обрыв). Живой сбор —
через `bank_geo_collect.py` БЕЗ VPN; флаг --fixtures берёт страницы последнего зонда
bank_geo_out2/ (первичное наполнение). Без флага и без бел. IP — честный 0.
Лучший банк-источник для обзвона: 32 лота, у КАЖДОГО телефоны + имена контактов.
Ядро parse_belarusbank — GLM (петля делегатов), фиксы Claude: float("...руб.") падал;
значение droppable-поля — голый текстовый узел, GLM собирал только теги.

Запуск: ./bin/python belarusbank_bank.py [--fixtures]  → banks_belarusbank.xlsx
"""
import argparse
import re
import socket
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

import auctions_common as A

BASE = "https://belarusbank.by"
LIST_URL = BASE + "/o-banke/property/client-property/nedvizhimost/"
FIXTURE = Path(__file__).parent / "bank_geo_out2/belarusbank/o-banke_property_client-property_nedvizhimost.html"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


# --- ядро (GLM через delegate_loop 03.07.2026 + фиксы Claude) ---
from typing import Dict, List

def parse_belarusbank(html: str) -> List[Dict]:
    """Лоты недвижимости Беларусбанка (каталог client-property/nedvizhimost). list[dict]."""
    if not html:
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    lots = soup.find_all('div', class_='lot item-lot')
    items = []
    
    for lot in lots:
        title_tag = lot.find('p', class_='lot__title')
        if not title_tag or not title_tag.get_text(strip=True):
            continue
        
        item = {
            'title': title_tag.get_text(strip=True),
            'kind': '',
            'address': '',
            'price': None,
            'phones': [],
            'contacts': [],
            'area': None,
            'year': '',
            'photo': ''
        }
        
        kind_tag = lot.find('span', class_='lot__status')
        if kind_tag:
            item['kind'] = kind_tag.get_text(strip=True)
        
        address_tag = lot.find('p', class_='lot__descr_address')
        if address_tag:
            item['address'] = address_tag.get_text(strip=True)
        
        price_tag = lot.find('p', class_='lot__descr_price')
        if price_tag:
            price_text = price_tag.get_text(strip=True).replace('\xa0', '').replace(' ', '')
            m = re.search(r'\d+(?:[.,]\d{1,2})?', price_text)  # fix Claude: float("...руб.") падал
            if m:
                try:
                    item['price'] = float(m.group(0).replace(',', '.'))
                except ValueError:
                    pass
        
        contact_tag = lot.find('p', class_='lot__descr_contact')
        if contact_tag:
            for span in contact_tag.find_all('span'):
                name = span.get_text(strip=True)
                if name:
                    item['contacts'].append(name)
            
            for a in contact_tag.find_all('a', href=True):
                href = a.get('href', '')
                if href.startswith('tel:'):
                    phone = href[4:]
                    if phone and phone not in item['phones']:
                        item['phones'].append(phone)
        
        slider_div = lot.find('div', class_='lot__slider swiper')
        if slider_div:
            first_img = slider_div.find('img')
            if first_img and first_img.get('src'):
                item['photo'] = first_img.get('src', '')
        
        droppable_titles = lot.find_all('p', class_='lot__droppable_title')
        for title_p in droppable_titles:
            label = title_p.get_text(strip=True).lower()
            value = ''
            sibling = title_p.next_sibling
            while sibling:
                nm = getattr(sibling, 'name', None)
                if nm in ('br', 'p'):
                    break
                # fix Claude: значение — ГОЛЫЙ текстовый узел (name=None), GLM его отбрасывал
                value += sibling if isinstance(sibling, str) else sibling.get_text(' ', strip=True)
                sibling = sibling.next_sibling
            
            value = value.replace('\xa0', '').strip()
            if 'площадь' in label and ('строений' in label or 'помещени' in label):
                try:
                    item['area'] = float(value.replace(',', '.').replace(' ', ''))
                except ValueError:
                    pass
            elif 'год постройки' in label:
                item['year'] = value
        
        items.append(item)
    
    return items
# --- конец ядра ---


# ===== слой 2: имущество САМОГО банка (bank-property) — страницы-аукционы =====
BP_URLS = [BASE + "/o-banke/property/bank-property/",
           BASE + "/o-banke/property/bank-property/?PAGEN_3=2"]
FIXDIR = Path(__file__).parent / "bank_geo_out2/belarusbank"
RE_ESTATE = re.compile(r"(?i)капитальн|помещени|недвижимост|здани|строени")


def _slug(url: str) -> str:
    """URL → имя файла фикстуры (та же схема, что в bank_geo_probe2)."""
    s = re.sub(r"https?://[^/]+", "", url).strip("/") or "index"
    return re.sub(r"[^a-zA-Z0-9а-яА-Я._-]+", "_", s)[:120]


def parse_bank_property_listing(html):
    """Карточки листинга bank-property: <div class="lot"> (БЕЗ item-lot, в отличие
    от каталога клиентов). Берём только недвижимость (title), мимо шин и мазд."""
    if not html:
        return []
    out = []
    for lot in BeautifulSoup(html, "html.parser").find_all("div", class_="lot"):
        t = lot.find("p", class_="lot__title")
        a = lot.find("a", class_="lot__btn-transp")
        if not t or not a:
            continue
        title = t.get_text(strip=True)
        if not RE_ESTATE.search(title):
            continue
        addr = lot.find("p", class_="lot__descr_address")
        phones = [x["href"][4:].strip() for x in lot.find_all("a", href=re.compile(r"^tel:"))]
        out.append({"title": title, "href": a["href"],
                    "address": addr.get_text(strip=True) if addr else "",
                    "phones": phones})
    return out


def _money(s):
    """'1 913,14 (Одна тысяча…)' → 1913.14; None если ячейка не денежная."""
    m = re.match(r"\s*([\d\s\xa0]{1,15}(?:,\d{2})?)\s*(?:\(|бел|руб|$)", s)
    if not m or not re.search(r"\d", m.group(1)):
        return None
    try:
        v = float(m.group(1).replace(" ", "").replace("\xa0", "").replace(",", "."))
    except ValueError:
        return None
    return v if v >= 10 else None   # отсечь номера лотов (1, 2, …)


def parse_bank_property_detail(html):
    """Извещение об аукционе. Одиночное — поля по меткам; МНОГОЛОТОВОЕ (таблица
    «№|Наименование|Начальная цена|Задаток», как у mgcn) — взрываем в lots[]."""
    d = {"lots": []}
    if not html:
        return d
    soup = BeautifulSoup(html, "html.parser")
    text = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    m = re.search(r"Дата проведения аукциона[^0-9]{0,20}(\d{2}\.\d{2}\.\d{4})", text)
    d["date"] = m.group(1) if m else ""

    for table in soup.find_all("table"):
        if "Начальная цена" not in table.get_text()[:400]:
            continue
        for tr in table.find_all("tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(tds) < 3:
                continue
            name = max(tds, key=len)
            if "Начальная цена" in name or not re.search(r"(?i)строени|помещени|здани", name):
                continue
            moneys = [v for c in tds if c != name for v in [_money(c)] if v is not None]
            ma = re.search(r"площадью:?\s*([\d\s\xa0]+(?:[.,]\d+)?)\s*кв", name)
            mr = re.search(r"адресу:?\s*(.{5,120}?)(?:,\s*общей|площадью|$)", name)
            d["lots"].append({
                "name": name[:200],
                "address": mr.group(1).strip(" ,") if mr else "",
                "area": float(ma.group(1).replace(" ", "").replace("\xa0", "").replace(",", ".")) if ma else None,
                "price": moneys[0] if moneys else None,
                "deposit": moneys[1] if len(moneys) > 1 else None,
            })
        if d["lots"]:
            return d

    # одиночное извещение
    def num(pat):
        m2 = re.search(pat, text)
        if not m2:
            return None
        try:
            return float(m2.group(1).replace(" ", "").replace("\xa0", "").replace(",", "."))
        except ValueError:
            return None

    d["price"] = num(r"Начальная цена[^0-9]{0,80}([\d\s\xa0]{3,}(?:,\d{2})?)")
    d["deposit"] = num(r"Сумма задатка[^0-9]{0,40}([\d\s\xa0]{3,}(?:,\d{2})?)")
    d["area"] = num(r"площадью\s*([\d\s\xa0]+(?:[.,]\d+)?)\s*кв")
    return d


def _get(url: str, use_fixtures: bool) -> str:
    if use_fixtures:
        f = FIXDIR / f"{_slug(url)}.html"
        if f.exists():
            return f.read_text(encoding="utf-8")
        print(f"  ⚠ нет фикстуры {f.name} — пропуск")
        return ""
    try:
        req = urllib.request.Request(url, headers=UA)
        return urllib.request.urlopen(req).read().decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        print(f"  ⚠ {type(e).__name__}: {url[:70]}")
        return ""


def collect_bank_property(use_fixtures: bool) -> list:
    items = []
    for lu in BP_URLS:
        for card in parse_bank_property_listing(_get(lu, use_fixtures)):
            durl = BASE + card["href"] if card["href"].startswith("/") else card["href"]
            det = parse_bank_property_detail(_get(durl, use_fixtures))

            def base_item(det=det, card=card, durl=durl):
                it = A.blank_item("belarusbank.by")
                it["Тип торгов"] = "Аукцион банка"
                it["Дата аукциона"] = det.get("date", "")
                it["Телефон"] = ", ".join(card["phones"])
                it["Организатор"] = "ОАО «АСБ Беларусбанк»"
                it["Ссылка"] = durl
                return it

            if det["lots"]:   # многолотовое извещение → каждый лот отдельной строкой
                for lot in det["lots"]:
                    it = base_item()
                    it["Объект"] = lot["name"]
                    it["Адрес"] = lot["address"]
                    it["Площадь, м²"] = str(lot["area"]) if lot["area"] else ""
                    it["Начальная цена"] = f"{lot['price']:.0f} BYN" if lot["price"] else ""
                    it["Задаток"] = f"{lot['deposit']:.0f} BYN" if lot["deposit"] else ""
                    it["Хэш"] = A.make_hash(durl, lot["name"])
                    items.append(it)
            else:
                it = base_item()
                it["Объект"] = card["title"][:200]
                it["Адрес"] = card["address"]
                it["Площадь, м²"] = str(det["area"]) if det.get("area") else ""
                it["Начальная цена"] = f"{det['price']:.0f} BYN" if det.get("price") else ""
                it["Задаток"] = f"{det['deposit']:.0f} BYN" if det.get("deposit") else ""
                it["Хэш"] = A.make_hash(durl)
                items.append(it)
    # дедуп: один аукцион может светиться на обеих страницах пагинации
    seen, uniq = set(), []
    for it in items:
        if it["Хэш"] in seen:
            continue
        seen.add(it["Хэш"])
        uniq.append(it)
    return uniq
# ===== конец слоя 2 =====


def get_html(use_fixtures: bool) -> str:
    if not use_fixtures:
        socket.setdefaulttimeout(20)
        try:
            req = urllib.request.Request(LIST_URL, headers=UA)
            return urllib.request.urlopen(req).read().decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001
            print(f"  ⚠ живой сайт недоступен ({type(e).__name__}) — гео-блок? Запусти без VPN "
                  f"или с --fixtures")
            return ""
    if FIXTURE.exists():
        print(f"  (данные из фикстуры зонда: {FIXTURE.name})")
        return FIXTURE.read_text(encoding="utf-8")
    print("  ⚠ фикстуры нет — сначала прогнать bank_geo_probe2.py без VPN")
    return ""


def collect(use_fixtures: bool) -> list:
    html = get_html(use_fixtures)
    items = []
    for lot in parse_belarusbank(html):
        it = A.blank_item("belarusbank.by")
        it["Тип торгов"] = "Продажа банком"
        it["Объект"] = lot["title"][:200]
        it["Адрес"] = lot["address"]
        it["Площадь, м²"] = str(lot["area"]) if lot.get("area") else ""
        it["Начальная цена"] = f"{lot['price']:.0f} BYN" if lot.get("price") else ""
        it["Телефон"] = ", ".join(lot.get("phones") or [])
        contacts = ", ".join(lot.get("contacts") or [])
        extra = [x for x in (lot.get("kind"), f"Год: {lot['year']}" if lot.get("year") else "",
                             f"Контакты: {contacts}" if contacts else "") if x]
        it["Описание"] = ". ".join(extra)
        it["Организатор"] = "ОАО «АСБ Беларусбанк»"
        it["Ссылка"] = LIST_URL
        it["Фото URL"] = BASE + lot["photo"] if lot.get("photo") else ""
        it["Хэш"] = A.make_hash(LIST_URL, it["Объект"], it["Адрес"])
        items.append(it)
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixtures", action="store_true", help="взять HTML из bank_geo_out2 (без сети)")
    cfg = ap.parse_args()
    out = Path("banks_belarusbank.xlsx").resolve()
    items = collect(cfg.fixtures)
    bp = collect_bank_property(cfg.fixtures)
    print(f"[BELARUSBANK] лоты клиентов: {len(items)}, аукционы банка: {len(bp)}")
    items += bp
    if items:
        A.write_excel(items, out, prev_hashes=set())
        for c in ("Объект", "Начальная цена", "Адрес", "Площадь, м²", "Телефон", "Фото URL"):
            n = sum(1 for r in items if r.get(c))
            print(f"  {c:16}: {n}/{len(items)} ({100 * n // len(items)}%)")


if __name__ == "__main__":
    main()

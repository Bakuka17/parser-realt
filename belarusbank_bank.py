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
from typing import List, Dict, Optional

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
    print(f"[BELARUSBANK] лотов: {len(items)}")
    if items:
        A.write_excel(items, out, prev_hashes=set())
        for c in ("Объект", "Начальная цена", "Адрес", "Площадь, м²", "Телефон", "Фото URL"):
            n = sum(1 for r in items if r.get(c))
            print(f"  {c:16}: {n}/{len(items)} ({100 * n // len(items)}%)")


if __name__ == "__main__":
    main()

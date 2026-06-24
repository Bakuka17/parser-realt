"""ipmtorgi_auctions — парсер аукционов ipmtorgi.by (недвижимость).

Серверный HTML (Bitrix). Список: /auctions/filter/section-is-nedvizhimost/apply/
с пагинацией PAGEN_1. Детальная страница даёт объект (h1), адрес, площадь, цену,
дату, задаток, организатора, телефон.

Чекпойнты+резюм (как у mgcn): прогресс пишется в .tmp.xlsx каждые N лотов, финал —
атомарный os.replace(tmp→out). При обрыве рестарт подхватывает .tmp и добирает остаток.

Запуск:  ./bin/python ipmtorgi_auctions.py
"""
import os
import random
import re
import time
from pathlib import Path

import auctions_common as A


CHECKPOINT_EVERY = 20  # сохранять прогресс каждые N лотов (защита от обрыва)


def collect(skip_urls: set, on_checkpoint=None) -> list[dict]:
    """Собирает лоты недвижимости, пропуская URL из skip_urls (резюм после обрыва).
    on_checkpoint(new) — периодический сейв прогресса."""
    new = []
    seen = set()
    base = "https://ipmtorgi.by/auctions/filter/section-is-nedvizhimost/apply/"
    detail_re = re.compile(r'href="((?:https://ipmtorgi\.by)?/auctions/nedvizhimost/[^"]+)"')
    prev_page_links: set = set()
    for page in range(1, 100):
        url = f"{base}?PAGEN_1={page}" if page > 1 else base
        print(f"[IPM] list p{page}")
        html = A.fetch(url)
        if not html: break
        links = [l for l in detail_re.findall(html) if l.rstrip('/').endswith('nedvizhimost') is False]
        if not links: break
        # Конец пагинации Bitrix: за последней страницей сайт отдаёт её же ещё раз.
        if set(links) == prev_page_links: break
        prev_page_links = set(links)
        new_on_page = 0
        for link in links:
            full = link if link.startswith("http") else "https://ipmtorgi.by" + link
            nu = A.norm_url(full)
            if nu in seen or nu in skip_urls: continue
            seen.add(nu); new_on_page += 1
            dhtml = A.fetch(full)
            if not dhtml: continue
            text = A.get_text(dhtml, multiline=True)
            it = A.blank_item("ipmtorgi.by")
            it["Ссылка"] = nu
            it["Тип торгов"] = "Аукцион"
            m = re.search(r'<h1[^>]*>(.*?)</h1>', dhtml, re.I|re.S)
            if m: it["Объект"] = A.clean(re.sub(r'<[^>]+>','',m.group(1)))
            if not it["Объект"]:
                m=re.search(r'<title>(.*?)</title>',dhtml,re.I|re.S)
                if m: it["Объект"]=A.clean(re.sub(r'<[^>]+>','',m.group(1)).split('|')[0])
            if not it["Объект"]: continue
            it["Адрес"] = A.extract_address(text) or ""
            ar = A.extract_area(text)
            it["Площадь, м²"] = str(ar) if ar else ""
            it["Начальная цена"]=A.extract_start_price(text)
            it["Дата аукциона"] = A.parse_date(text)
            md = re.search(r'(?i)задат\w+.{0,60}?(\d[\d\s]*[.,]?\d*)\s*(?:BYN|бел\.?\s*руб|Br)', text)
            it["Задаток"] = A.parse_price(md.group(0)) if md else ""
            mo = re.search(r'(?i)организатор[:\s\-]*([^\n\.]{5,80})', text)
            it["Организатор"] = A.clean(mo.group(1)) if mo else ""
            it["Телефон"] = A.extract_phones(text)
            it["Хэш"] = A.make_hash(nu, it["Объект"])
            new.append(it)
            print(f"  + {it['Объект'][:45]} | цена={it['Начальная цена'] or '—'}")
            if on_checkpoint and len(new) % CHECKPOINT_EVERY == 0:
                on_checkpoint(new)
            time.sleep(random.uniform(1.0, 2.0))
        # ⚠ НЕ break при new_on_page==0: на РЕЗЮМЕ первые страницы уже собраны
        # (skip_urls), это не конец пагинации. Конец ловим выше: пустая страница
        # или повтор предыдущей.
    return new


def main():
    out = Path("auctions_ipmtorgi.xlsx").resolve()
    tmp = out.with_suffix(".tmp.xlsx")
    # Резюм: незавершённый .tmp от обрыва — продолжаем с него. Иначе с нуля
    # (старый out содержит истёкшие лоты — заменяем целиком свежими).
    base = A.load_prev(tmp) if tmp.exists() else {}
    if base:
        print(f"♻ найден чекпойнт ({len(base)} лотов) — продолжаю с него")
    base_vals = list(base.values())
    skip_urls = set(base.keys())
    snapshot = {str(r.get("Хэш")) for r in base.values() if r.get("Хэш")}

    def save(items: list[dict], final: bool = False) -> None:
        """Атомарно: пишем в .tmp, в финале переименовываем в out."""
        A.write_excel(base_vals + items, tmp, prev_hashes=snapshot)
        if final:
            os.replace(tmp, out)
        else:
            print(f"  💾 чекпойнт: всего {len(base_vals) + len(items)} (новых {len(items)})")

    new = collect(skip_urls, on_checkpoint=lambda items: save(items))
    print(f"\n[IPM] лотов: {len(base_vals) + len(new)} (новых: {len(new)})")
    save(new, final=True)
    res = base_vals + new
    if res:
        for c in A.AUCTION_COLUMNS:
            n = sum(1 for r in res if r.get(c))
            print(f"  {c:18}: {n}/{len(res)} ({100 * n // len(res)}%)")


if __name__ == "__main__":
    main()

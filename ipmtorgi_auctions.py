import re
from pathlib import Path
import auctions_common as A

def get_text(html):
    if not html: return ""
    text = re.sub(r'<script.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<style.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', '\n', text)
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

def parse_ipmtorgi():
    items = []
    seen = set()
    base = "https://ipmtorgi.by/auctions/filter/section-is-nedvizhimost/apply/"
    # ссылки бывают абсолютные и относительные; «голую» категорию пропускаем
    detail_re = re.compile(r'href="((?:https://ipmtorgi\.by)?/auctions/nedvizhimost/[^"]+)"')
    for page in range(1, 100):
        url = f"{base}?PAGEN_1={page}" if page > 1 else base
        print(f"[IPM] list p{page}")
        html = A.fetch(url)
        if not html: break
        links = [l for l in detail_re.findall(html) if l.rstrip('/').endswith('nedvizhimost') is False]
        if not links: break
        new_on_page = 0
        for link in links:
            full = link if link.startswith("http") else "https://ipmtorgi.by" + link
            nu = A.norm_url(full)
            if nu in seen: continue
            seen.add(nu); new_on_page += 1
            dhtml = A.fetch(full)
            if not dhtml: continue
            text = get_text(dhtml)
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
            it["Площадь, м²"] = str(ar) if ar else ""        # ФИКС: верный ключ
            # цена: ищем рядом со словом «начальн … цен»
            mp = re.search(r'начальн\w*\s+цен\w*.{0,80}?(\d[\d\s]*[.,]?\d*)\s*(?:BYN|бел\.?\s*руб|Br)', text, re.I)
            it["Начальная цена"]=A.extract_start_price(text)
            it["Дата аукциона"] = A.parse_date(text)
            md = re.search(r'(?i)задат\w+.{0,60}?(\d[\d\s]*[.,]?\d*)\s*(?:BYN|бел\.?\s*руб|Br)', text)
            it["Задаток"] = A.parse_price(md.group(0)) if md else ""
            mo = re.search(r'(?i)организатор[:\s\-]*([^\n\.]{5,80})', text)
            it["Организатор"] = A.clean(mo.group(1)) if mo else ""
            it["Телефон"] = A.extract_phones(text)
            it["Хэш"] = A.make_hash(nu, it["Объект"])     # ФИКС: верный ключ
            items.append(it)
            print(f"  + {it['Объект'][:45]} | цена={it['Начальная цена'] or '—'}")
            import time, random; time.sleep(random.uniform(1.0,2.0))
        if new_on_page == 0: break
    return items

if __name__ == "__main__":
    res = parse_ipmtorgi()
    print(f"\n[IPM] лотов: {len(res)}")
    if res:
        for c in A.AUCTION_COLUMNS:
            n=sum(1 for r in res if r.get(c))
            print(f"  {c:18}: {n}/{len(res)} ({100*n//len(res)}%)")
    A.write_excel(res, Path("auctions_ipmtorgi.xlsx"))

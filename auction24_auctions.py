import re, time, random
from pathlib import Path
import auctions_common as A

def get_text(html):
    if not html: return ""
    t=re.sub(r'<script.*?</script>','',html,flags=re.S|re.I)
    t=re.sub(r'<style.*?</style>','',t,flags=re.S|re.I)
    t=re.sub(r'<[^>]+>','\n',t); t=re.sub(r'[ \t]+',' ',t); t=re.sub(r'\n\s*\n','\n',t)
    return t.strip()

def parse():
    items=[]; seen=set()
    html=A.fetch("https://auction24.by/")
    if not html: print("список не скачался"); return items
    links=list(dict.fromkeys(re.findall(r'href="((?:https?://auction24.by)?/auction/\d+[^"]*)"', html)))
    print(f"ссылок: {len(links)}")
    for link in links:
        full=link if link.startswith("http") else "https://auction24.by"+link
        nu=A.norm_url(full)
        if nu in seen: continue
        seen.add(nu)
        d=A.fetch(full)
        if not d: continue
        text=get_text(d)
        it=A.blank_item("auction24.by"); it["Ссылка"]=nu; it["Тип торгов"]="Аукцион"
        m=re.search(r'<h1[^>]*>(.*?)</h1>', d, re.S|re.I)
        if m: it["Объект"]=A.clean(re.sub(r'<[^>]+>','',m.group(1)))
        if not it["Объект"]:
            m=re.search(r'<title>(.*?)</title>',d,re.S|re.I)
            if m: it["Объект"]=A.clean(re.sub(r'<[^>]+>','',m.group(1)).split('|')[0])
        if not it["Объект"]: continue
        it["Адрес"]=A.extract_address(text) or ""
        ar=A.extract_area(text); it["Площадь, м²"]=str(ar) if ar else ""
        it["Начальная цена"]=A.extract_start_price(text)
        it["Дата аукциона"]=A.parse_date(it["Объект"]) or A.parse_date(text)
        it["Телефон"]=A.extract_phones(text)
        it["Хэш"]=A.make_hash(nu, it["Объект"])
        items.append(it)
        time.sleep(random.uniform(1.0,2.0))
    return items

if __name__=="__main__":
    res=parse(); print(f"[auction24] лотов: {len(res)}")
    if res:
        for c in A.AUCTION_COLUMNS:
            n=sum(1 for r in res if r.get(c)); print(f"  {c:18}: {100*n//len(res)}%")
        print("примеры:")
        for r in res[:3]: print("  ",(r['Объект'] or '')[:42],'| цена',r['Начальная цена'] or '—','| дата',r['Дата аукциона'] or '—')
    A.write_excel(res, Path("auctions_auction24.xlsx"))

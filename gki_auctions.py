import re, time, random
from pathlib import Path
import auctions_common as A

def get_text(html):
    if not html: return ""
    t=re.sub(r'<script.*?</script>','',html,flags=re.S|re.I)
    t=re.sub(r'<style.*?</style>','',t,flags=re.S|re.I)
    t=re.sub(r'<[^>]+>','\n',t); t=re.sub(r'[ \t]+',' ',t); t=re.sub(r'\n\s*\n','\n',t)
    return t.strip()

def parse_gki():
    items=[]; seen=set()
    sections=[("https://gki.gov.by/ru/auction-auinf_live/","Аукцион"),
              ("https://gki.gov.by/ru/dop-zem/","Аукцион (земля)")]
    detail_re=re.compile(r'href="([^"]*view/izvesch[^"]*)"')
    for base,atype in sections:
        print(f"[GKI] {base}")
        html=A.fetch(base)
        if not html: continue
        for link in dict.fromkeys(detail_re.findall(html)):
            full=link if link.startswith("http") else "https://gki.gov.by"+link
            nu=A.norm_url(full)
            if nu in seen: continue
            seen.add(nu)
            d=A.fetch(full)
            if not d: continue
            text=get_text(d)
            it=A.blank_item("gki.gov.by"); it["Ссылка"]=nu; it["Тип торгов"]=atype
            m=re.search(r'<title>(.*?)</title>',d,re.I|re.S)
            if m: it["Объект"]=A.clean(re.sub(r'<[^>]+>','',m.group(1)).split('|')[0])
            if not it["Объект"]:
                m=re.search(r'<h1[^>]*>(.*?)</h1>',d,re.I|re.S)
                if m: it["Объект"]=A.clean(re.sub(r'<[^>]+>','',m.group(1)))
            if not it["Объект"]: continue
            it["Адрес"]=A.extract_address(text) or ""
            ar=A.extract_area(text); it["Площадь, м²"]=str(ar) if ar else ""
            it["Начальная цена"]=A.extract_start_price(text)
            it["Дата аукциона"]=A.parse_date(text)
            mo=re.search(r'(?i)организатор[:\s\-]*([^\n\.]{5,80})',text)
            it["Организатор"]=A.clean(mo.group(1)) if mo else ""
            it["Телефон"]=A.extract_phones(text)
            it["Хэш"]=A.make_hash(nu,it["Объект"])
            items.append(it)
            time.sleep(random.uniform(1.0,2.0))
    return items

if __name__=="__main__":
    res=parse_gki(); print(f"[GKI] лотов: {len(res)}")
    if res:
        for c in A.AUCTION_COLUMNS:
            n=sum(1 for r in res if r.get(c)); print(f"  {c:18}: {100*n//len(res)}%")
    A.write_excel(res, Path("auctions_gki.xlsx"))

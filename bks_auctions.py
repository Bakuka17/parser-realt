import re, time, random
from pathlib import Path
import auctions_common as A

def get_text(html):
    if not html: return ""
    t=re.sub(r'<script.*?</script>','',html,flags=re.S|re.I)
    t=re.sub(r'<style.*?</style>','',t,flags=re.S|re.I)
    t=re.sub(r'<[^>]+>','\n',t); t=re.sub(r'[ \t]+',' ',t); t=re.sub(r'\n\s*\n','\n',t)
    return t.strip()

def parse_bks():
    items=[]; seen=set()
    html=A.fetch("https://bks.gov.by/realties")
    if not html: return items
    for link in dict.fromkeys(re.findall(r'href="(https://bks\.gov\.by/realties/[^"]+|/realties/[^"]+)"',html)):
        full=link if link.startswith("http") else "https://bks.gov.by"+link
        nu=A.norm_url(full)
        if nu in seen or nu.rstrip('/').endswith('realties'): continue
        seen.add(nu)
        d=A.fetch(full)
        if not d: continue
        text=get_text(d)
        it=A.blank_item("bks.gov.by"); it["Ссылка"]=nu; it["Тип торгов"]="Аукцион"
        m=re.search(r'<h1[^>]*>(.*?)</h1>',d,re.I|re.S)
        if m: it["Объект"]=A.clean(re.sub(r'<[^>]+>','',m.group(1)))
        # на bks title = имя сайта, h3 = «Белкоопсоюз» → не годятся.
        # объект берём из URL-слага: brestskaya-...-baza → «Brestskaya ... Baza»
        site_junk = ("потребит" in it["Объект"].lower() or "белкооп" in it["Объект"].lower()
                     or not it["Объект"])
        if site_junk:
            slug = nu.rstrip("/").split("/")[-1]
            slug = re.sub(r"-\d+$", "", slug)          # убрать хвостовой -220
            it["Объект"] = slug.replace("-", " ").strip().capitalize()
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
    res=parse_bks(); print(f"[BKS] лотов: {len(res)}")
    if res:
        for c in A.AUCTION_COLUMNS:
            n=sum(1 for r in res if r.get(c)); print(f"  {c:18}: {100*n//len(res)}%")
    A.write_excel(res, Path("auctions_bks.xlsx"))

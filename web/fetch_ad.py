#!/usr/bin/env python3
"""До-фетч полной веб-версии объявления (заголовок, текст, все фото).

Источники: kufar (текст+фото из __NEXT_DATA__ adView), megapolis и realt
(описание из HTML-блока, фото из og:image-метатегов). Телефон у kufar за капчей —
не трогаем (он и так в строке Excel, где есть).

Используется бэкендом дашборда (web/server.py) для кнопки «Сохранить».
"""
import gzip
import json
import re
import urllib.request

from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.4 Safari/605.1.15")


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "ru,en;q=0.9", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return r.geturl(), raw.decode("utf-8", "replace")


def _og(soup, prop):
    m = soup.find("meta", property=prop)
    return (m.get("content") or "").strip() if m else ""


def _og_images(soup):
    out = []
    for m in soup.find_all("meta", property="og:image"):
        u = (m.get("content") or "").strip()
        if u.startswith("http") and u not in out and not re.search(
                r"logo|placeholder|default|sprite", u, re.I):
            out.append(u)
    return out


def _kufar(url):
    _, html = _get(url)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    if not m:
        return None
    d = json.loads(m.group(1))
    ad = d["props"]["initialState"]["adView"]["data"]
    title = ad.get("title") or ad.get("subject") or ""
    text = (ad.get("body") or ad.get("description")
            or (ad.get("initial") or {}).get("body") or "")
    photos = list((ad.get("gallery") or {}).get("images") or [])
    if not photos:
        for im in (ad.get("initial") or {}).get("images") or []:
            p = im.get("path")
            if p:
                photos.append(f"https://rms.kufar.by/v1/gallery/{p}")
    return {"title": title, "text": text, "photos": photos}


def _megapolis(url):
    _, html = _get(url)
    soup = BeautifulSoup(html, "lxml")
    title = _og(soup, "og:title") or (soup.title.string.strip() if soup.title else "")
    text = ""
    blk = soup.find(class_=re.compile(r"info_block_descripti"))
    if blk:
        text = re.sub(r"^\s*Описание объекта\s*", "", blk.get_text(" ", strip=True))
    return {"title": title, "text": text, "photos": _og_images(soup)}


def _realt(url):
    _, html = _get(url)
    soup = BeautifulSoup(html, "lxml")
    title = _og(soup, "og:title") or (soup.title.string.strip() if soup.title else "")
    # описание — самый длинный блок с классом text-clamp; иначе og:description
    text = ""
    best = 0
    for blk in soup.find_all(class_=re.compile(r"text-clamp")):
        t = blk.get_text(" ", strip=True)
        if len(t) > best:
            best, text = len(t), t
    if len(text) < 40:
        text = _og(soup, "og:description") or text
    return {"title": title, "text": text, "photos": _og_images(soup)}


def first_og_image(url, timeout=15):
    """Лёгкий вариант: только первое og:image страницы (для превью-карточек)."""
    try:
        _, html = _get(url, timeout=timeout)
        soup = BeautifulSoup(html, "lxml")
        imgs = _og_images(soup)
        return imgs[0] if imgs else ""
    except Exception:  # noqa: BLE001 — сеть/антибот: просто нет превью
        return ""


def fetch_full_ad(url):
    """-> {ok, error, title, text, photos[]}. Никогда не кидает исключение."""
    base = {"ok": False, "error": "", "title": "", "text": "", "photos": []}
    try:
        host = url.split("/")[2]
    except (IndexError, AttributeError):
        return {**base, "error": "плохой url"}
    try:
        if "kufar" in host:
            r = _kufar(url)
        elif "megapolis" in host:
            r = _megapolis(url)
        elif "realt.by" in host:
            r = _realt(url)
        else:
            return {**base, "error": f"источник не поддержан: {host}"}
        if not r:
            return {**base, "error": "не нашёл данные на странице"}
        return {**base, **r, "ok": True}
    except Exception as e:  # noqa: BLE001 — сеть/парсинг, отдаём мягко
        return {**base, "error": f"{type(e).__name__}: {e}"}


if __name__ == "__main__":
    import sys
    res = fetch_full_ad(sys.argv[1])
    res2 = {**res, "text": res["text"][:160] + "…", "photos": res["photos"][:3]}
    print(json.dumps(res2, ensure_ascii=False, indent=2))
    print("фото всего:", len(res["photos"]), "| текст длина:", len(res["text"]))

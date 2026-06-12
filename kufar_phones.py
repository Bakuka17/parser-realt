#!/usr/bin/env python3
"""Добор телефонов kufar в commercial_realty.xlsx.

⚠️ ЗАПУСКАТЬ С ВЫКЛЮЧЕННЫМ Psiphon (нужен белорусский IP — иначе kufar прячет номер).

Как работает: берёт kufar-объявления без телефона прямо из xlsx, открывает деталку,
жмёт «Позвонить»/«Показать телефон» (reCAPTCHA v3 проходит сама), ловит ответ
api.kufar.by/.../phone и дописывает номер в колонку «Телефон» той же строки.
Существующие телефоны не трогает. Можно прерывать и запускать снова — продолжит
с оставшихся пустых (естественный резюм).

  ./bin/python kufar_phones.py --limit 25      # первый безопасный прогон
  ./bin/python kufar_phones.py                 # все оставшиеся
  ./bin/python kufar_phones.py --headless      # без видимого окна (рискованнее для капчи)

После добора обновите дашборд: ./bin/python web/export_data.py
"""
import argparse
import asyncio
import json
import random
import re
import shutil
import time
import urllib.request
from pathlib import Path

from openpyxl import load_workbook
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
MAIN_XLSX = HERE / "commercial_realty.xlsx"
SHEETS = ("Продажа", "Аренда")
CHECKPOINT_EVERY = 20          # сохранять xlsx каждые N добытых номеров
CTX_RESET_EVERY = 250          # новый контекст браузера (свежий fingerprint)
PHONE_BTN = ["text=Позвонить", "text=Показать телефон", "text=Показать номер",
             "button:has-text('Показать')"]
USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/16.4 Safari/605.1.15",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
]


def split_phones(raw):
    """Сырьё (может содержать НЕСКОЛЬКО слитых номеров) → список '+375XXXXXXXXX'.

    У объявления бывает 2-3 телефона; kufar отдаёт их подряд. Режем по канону
    бел. номера 375+9 цифр; запасные форматы 80… и общий — одиночные.
    """
    digits = re.sub(r"\D", "", raw or "")
    out = []
    for m in re.findall(r"375\d{9}", digits):       # точная нарезка слипшихся
        p = "+" + m
        if p not in out:
            out.append(p)
    if not out and digits.startswith("80") and len(digits) >= 11:
        out.append("+375" + digits[2:11])
    if not out and digits:
        out.append("+" + digits)
    return out


def norm_phone(raw):
    """Один или несколько номеров → строка через запятую (формат проекта)."""
    return ", ".join(split_phones(raw))


def exit_country():
    """Страна нашего внешнего IP. -> (countryCode, country, ip) или (None,None,None)."""
    try:
        req = urllib.request.Request(
            "http://ip-api.com/json/?fields=country,countryCode,query",
            headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.load(r)
        return d.get("countryCode"), d.get("country", "?"), d.get("query", "?")
    except Exception:
        return None, None, None


def guard_belarus_ip(force):
    """True = можно работать. Под Psiphon (иностранный IP) kufar прячет телефон —
    тратить часы впустую незачем, поэтому при не-белорусском IP останавливаемся."""
    if force:
        print("⚠ Проверка IP пропущена (--force).")
        return True
    cc, country, ip = exit_country()
    if cc is None:
        print("⚠ Не удалось определить страну IP — продолжаю. Если Psiphon включён,"
              " номера НЕ раскроются (тогда прервите и выключите VPN).")
        return True
    if cc != "BY":
        print(f"⛔ Внешний IP — {country} ({ip}), НЕ Беларусь.\n"
              f"   kufar прячет телефоны для иностранных IP. ВЫКЛЮЧИТЕ Psiphon и повторите.\n"
              f"   (обойти проверку, если уверены: --force)")
        return False
    print(f"✓ IP белорусский ({ip}) — kufar отдаст телефоны.")
    return True


def collect_targets(ws, limit):
    """(row_idx, url) для kufar-строк без телефона. row_idx — 1-based для openpyxl."""
    hdr = [c.value for c in ws[2]]
    col = {str(h): i for i, h in enumerate(hdr) if h}
    ph, lk, sr = col.get("Телефон"), col.get("Ссылка"), col.get("Источник")
    if ph is None or lk is None or sr is None:
        return []
    out = []
    for r in range(3, ws.max_row + 1):
        if "kufar" not in str(ws.cell(r, sr + 1).value or ""):
            continue
        if str(ws.cell(r, ph + 1).value or "").strip():
            continue
        url = str(ws.cell(r, lk + 1).value or "")
        if url.startswith("http"):
            out.append((r, url, ph + 1))
        if limit and len(out) >= limit:
            break
    return out


async def get_phone(page, url):
    """Открыть деталку, раскрыть номер. Возвращает нормализованный телефон или ''."""
    caught = []  # все номера из ответов /phone (у объявления их может быть несколько)

    async def on_resp(resp):
        if "/phone" in resp.url and resp.status == 200:
            try:
                j = await resp.json()
                v = j.get("phone") or j.get("phones")
                if v:
                    caught.append(v if isinstance(v, str) else ",".join(map(str, v)))
            except Exception:
                pass

    page.on("response", on_resp)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        for sel in PHONE_BTN:
            btn = page.locator(sel).first
            if await btn.count():
                try:
                    await btn.scroll_into_view_if_needed(timeout=2500)
                    await btn.click(timeout=3500)
                    break
                except Exception:
                    continue
        # ждём ответ /phone до ~6с
        for _ in range(12):
            if caught:
                break
            await page.wait_for_timeout(500)
        if not caught:  # fallback: все tel:-ссылки в DOM
            dom = await page.evaluate(r"""() => {
              const tels = [...document.querySelectorAll("a[href^='tel:']")]
                .map(a => a.getAttribute('href').replace('tel:',''));
              if (tels.length) return tels.join(',');
              const m = document.body.innerText.match(/\+375[\s\-()]?\d{2}[\s\-()]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}/g);
              return m ? m.join(',') : '';
            }""")
            if dom:
                caught.append(dom)
    finally:
        page.remove_listener("response", on_resp)
    return norm_phone(",".join(caught))


async def main():
    ap = argparse.ArgumentParser(description="Добор телефонов kufar (бел. IP, VPN OFF).")
    ap.add_argument("--limit", type=int, default=0, help="сколько объявлений за прогон (0 = все)")
    ap.add_argument("--headless", action="store_true", help="без видимого окна (рискованнее)")
    ap.add_argument("--force", action="store_true", help="не проверять страну IP")
    cfg = ap.parse_args()

    if not guard_belarus_ip(cfg.force):
        return

    if (HERE / "~$commercial_realty.xlsx").exists():
        print("⚠️  commercial_realty.xlsx открыт в Excel — закройте файл и повторите.")
        return

    print("Бэкап → commercial_realty.xlsx.bak")
    shutil.copy(MAIN_XLSX, MAIN_XLSX.with_suffix(".xlsx.bak"))

    wb = load_workbook(MAIN_XLSX)
    targets = []
    per = cfg.limit if cfg.limit else 0
    for sh in SHEETS:
        if sh in wb.sheetnames:
            need = (per - len(targets)) if per else 0
            if per and need <= 0:
                break
            targets += [(sh, *t) for t in collect_targets(wb[sh], need)]
    print(f"К добору: {len(targets)} kufar-объявлений без телефона"
          + (f" (лимит {cfg.limit})" if cfg.limit else "") + "\n")
    if not targets:
        print("Нечего добирать."); return

    got = empty = 0
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=cfg.headless)
        ctx = await browser.new_context(locale="ru-RU", user_agent=random.choice(USER_AGENTS))
        page = await ctx.new_page()

        for n, (sheet, row, url, ph_col) in enumerate(targets, 1):
            if n > 1 and n % CTX_RESET_EVERY == 0:        # свежий fingerprint
                await ctx.close()
                ctx = await browser.new_context(locale="ru-RU",
                                                user_agent=random.choice(USER_AGENTS))
                page = await ctx.new_page()
                print("   … сброс контекста браузера")

            try:
                phone = await get_phone(page, url)
            except Exception as e:
                phone = ""
                print(f"[{n}/{len(targets)}] {sheet}!{row}  ошибка: {type(e).__name__}")

            if phone:
                wb[sheet].cell(row=row, column=ph_col).value = phone
                got += 1
                print(f"[{n}/{len(targets)}] {sheet}!{row}  ✓ {phone}")
            else:
                empty += 1
                print(f"[{n}/{len(targets)}] {sheet}!{row}  — нет номера")

            if got and got % CHECKPOINT_EVERY == 0:
                wb.save(MAIN_XLSX)
                print(f"   💾 чекпойнт: сохранено (+{got} номеров)")

            await page.wait_for_timeout(int(random.uniform(2500, 6000)))  # пауза, как человек

        await browser.close()

    wb.save(MAIN_XLSX)
    print(f"\n📦 Готово: добыто {got}, без номера {empty} из {len(targets)}.")
    print(f"   файл: {MAIN_XLSX}")
    print("   Обновите дашборд:  ./bin/python web/export_data.py")


if __name__ == "__main__":
    t0 = time.time()
    asyncio.run(main())
    print(f"   время: {time.time() - t0:.0f}с")

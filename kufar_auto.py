#!/usr/bin/env python3
"""Автодобор телефонов kufar — запускается launchd раз в 4 часа.

Каждый заход: проверяет белорусский IP → есть ли что добирать → гонит порцию
(headless, залогиненным профилем) → ре-экспорт дашборда. Всё пишет в logs/kufar_auto.log.
Сам останавливается, когда бэклог исчерпан (остаётся только «телефона нет»).

⚠ Реально добирает ТОЛЬКО когда Psiphon ВЫКЛЮЧЕН (иначе kufar прячет номер) — при
иностранном IP заход пропускается с записью в лог, без вреда.

Управление: «Автодобор-вкл.command» / «Автодобор-выкл.command».
"""
import ast
import datetime
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "logs" / "kufar_auto.log"
STATS = HERE / "logs" / "kufar_stats.csv"  # замер: по строке на заход, для подбора интервала
LIMIT = 150  # сколько объявлений за один заход (≈25-30 мин)


def _kp():
    spec = importlib.util.spec_from_file_location("kufar_phones", HERE / "kufar_phones.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def log(msg):
    LOG.parent.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def save_stats(out, rem_after):
    """Строка замера в kufar_stats.csv — цифры выдёргиваются из отчёта kufar_phones."""
    m = re.search(r"добыто (\d+)", out)
    got = int(m.group(1)) if m else 0
    m = re.search(r"разбивка: ({.*})", out)
    rs = ast.literal_eval(m.group(1)) if m else {}
    m = re.search(r"время: (\d+)с", out)
    mins = int(m.group(1)) // 60 if m else 0
    row = [datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), LIMIT, got,
           rs.get("no_response", 0), rs.get("no_button", 0), rs.get("throttled", 0),
           rs.get("error", 0), int("придушивает" in out), mins, rem_after]
    new = not STATS.exists()
    with open(STATS, "a", encoding="utf-8") as f:
        if new:
            f.write("время,порция,добыто,no_response,no_button,throttled,error,бан_стоп,минут,остаток\n")
        f.write(",".join(map(str, row)) + "\n")


def main():
    m = _kp()
    cc, country, ip = m.exit_country()
    if cc != "BY":                       # None (не определил) или иностранный — пропуск
        log(f"пропуск: IP={country} ({ip}) — нужен белорусский (выключите Psiphon)")
        return
    py = sys.executable
    # Шаг 1: собрать свежие объявления kufar (инкрементал → новые строки без телефона
    # в конец базы). Добор ниже идёт «свежие первыми», так дневная квота уходит на новьё.
    log("шаг 1/2: сбор свежих объявлений kufar (collect_realty --sources kufar)")
    cr = subprocess.run([py, "collect_realty.py", "--sources", "kufar"],
                        cwd=str(HERE), capture_output=True, text=True)
    log("сбор: " + "\n".join((cr.stdout or "").strip().splitlines()[-3:]))
    rem = m.remaining_count()
    if rem == 0:
        log("✅ база телефонов kufar заполнена — добирать нечего (можно выключить автодобор)")
        return
    log(f"шаг 2/2: добор телефонов — остаток {rem}, гоню порцию {LIMIT} (свежие первыми)")
    # --chrome-cookies обязателен с 14.06: kufar спрятал телефон за логин-стену,
    # сессию берём из обычного Chrome (держать аккаунт залогиненным)
    r = subprocess.run([py, "kufar_phones.py", "--limit", str(LIMIT), "--headless", "--force",
                        "--chrome-cookies"],
                       cwd=str(HERE), capture_output=True, text=True)
    tail = "\n".join((r.stdout or "").strip().splitlines()[-6:])
    log("результат:\n" + tail + ("\n[stderr] " + r.stderr.strip()[-300:] if r.stderr.strip() else ""))
    subprocess.run([py, "web/export_data.py"], cwd=str(HERE), capture_output=True, text=True)
    rem_after = m.remaining_count()
    save_stats(r.stdout or "", rem_after)
    log(f"готово, осталось ~{rem_after}; замер → {STATS.name}")


if __name__ == "__main__":
    main()

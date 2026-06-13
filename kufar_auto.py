#!/usr/bin/env python3
"""Автодобор телефонов kufar — запускается launchd раз в 4 часа.

Каждый заход: проверяет белорусский IP → есть ли что добирать → гонит порцию
(headless, залогиненным профилем) → ре-экспорт дашборда. Всё пишет в logs/kufar_auto.log.
Сам останавливается, когда бэклог исчерпан (остаётся только «телефона нет»).

⚠ Реально добирает ТОЛЬКО когда Psiphon ВЫКЛЮЧЕН (иначе kufar прячет номер) — при
иностранном IP заход пропускается с записью в лог, без вреда.

Управление: «Автодобор-вкл.command» / «Автодобор-выкл.command».
"""
import datetime
import importlib.util
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "logs" / "kufar_auto.log"
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


def main():
    m = _kp()
    cc, country, ip = m.exit_country()
    if cc != "BY":                       # None (не определил) или иностранный — пропуск
        log(f"пропуск: IP={country} ({ip}) — нужен белорусский (выключите Psiphon)")
        return
    rem = m.remaining_count()
    if rem == 0:
        log("✅ база телефонов kufar заполнена — добирать нечего (можно выключить автодобор)")
        return
    log(f"старт: остаток {rem}, гоню порцию {LIMIT}")
    py = sys.executable
    r = subprocess.run([py, "kufar_phones.py", "--limit", str(LIMIT), "--headless", "--force"],
                       cwd=str(HERE), capture_output=True, text=True)
    tail = "\n".join((r.stdout or "").strip().splitlines()[-6:])
    log("результат:\n" + tail + ("\n[stderr] " + r.stderr.strip()[-300:] if r.stderr.strip() else ""))
    subprocess.run([py, "web/export_data.py"], cwd=str(HERE), capture_output=True, text=True)
    log(f"готово, осталось ~{m.remaining_count()}")


if __name__ == "__main__":
    main()

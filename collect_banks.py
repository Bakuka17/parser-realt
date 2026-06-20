"""collect_banks — оркестратор банк-парсеров залоговой/непрофильной недвижимости.

Гонит каждый {name}_bank.py отдельным процессом (изоляция: падение одного не роняет
остальные). Каждый пишет banks_{name}.xlsx; export_data.load_banks() читает все banks_*.xlsx
по маске — новый банк-парсер подхватывается без правок дашборда.

  ./bin/python collect_banks.py
  ./bin/python collect_banks.py --only belinvest
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
PY = sys.executable

# по мере добавления парсеров: + "priorbank", "tcbank", "rrb", "zepter", ...
BANKS = ["belinvest"]


def run_bank(name: str) -> tuple[str, int, float]:
    script = HERE / f"{name}_bank.py"
    if not script.exists():
        print(f"  ⚠ {script.name} не найден — пропуск")
        return name, -1, 0.0
    print(f"\n{'=' * 64}\n▶ {name}\n{'=' * 64}")
    t0 = time.time()
    rc = subprocess.run([PY, "-u", str(script)], cwd=HERE).returncode
    dt = time.time() - t0
    print(f"  ⏱ {name}: {dt:.0f}с, код {rc}")
    return name, rc, dt


def main() -> None:
    ap = argparse.ArgumentParser(description="Оркестратор банк-парсеров → banks_*.xlsx")
    ap.add_argument("--only", help="только эти банки через запятую")
    cfg = ap.parse_args()
    sel = [s.strip() for s in cfg.only.split(",")] if cfg.only else list(BANKS)
    plan = [b for b in BANKS if b in sel]
    print(f"🏦 collect_banks | банков: {len(plan)} → {', '.join(plan)}")
    results = [run_bank(b) for b in plan]
    ok = sum(1 for _, rc, _ in results if rc == 0)
    print(f"\n✅ collect_banks готово: {ok}/{len(results)} успешно")


if __name__ == "__main__":
    main()

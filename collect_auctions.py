"""collect_auctions — единый оркестратор аукционов: ОДНА команда → все площадки → один свод.

Запускает каждый `{site}_auctions.py` (как отдельный процесс — изоляция и устойчивость:
падение одной площадки не роняет остальные), затем `merge_auctions.py` собирает всё
в `auctions_realty.xlsx` (дедуп по ссылке).

Примеры:
  ./bin/python collect_auctions.py                       # все площадки + свод
  ./bin/python collect_auctions.py --sources mgcn,torgigov
  ./bin/python collect_auctions.py --skip beltorgi,ipmtorgi
  ./bin/python collect_auctions.py --mgcn-full            # mgcn перепарсить целиком (адреса/площади)
  ./bin/python collect_auctions.py --no-merge            # без финального свода
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
PY = sys.executable  # интерпретатор текущего venv

# Порядок площадок (как в scheduled_run.sh). Сервер-HTML быстрые — раньше; тяжёлые — позже.
SITES = ["mgcn", "ipmtorgi", "torgi24", "auction24", "gki", "bks",
         "eauction", "deloocenka", "konfiskat", "torgigov", "beltorgi"]


def run_site(name: str, mgcn_full: bool) -> tuple[str, int, float]:
    script = HERE / f"{name}_auctions.py"
    if not script.exists():
        print(f"  ⚠ {script.name} не найден — пропуск")
        return name, -1, 0.0
    extra = ["--full"] if (name == "mgcn" and mgcn_full) else []
    print(f"\n{'=' * 64}\n▶ {name}{' '.join([''] + extra)}\n{'=' * 64}")
    t0 = time.time()
    rc = subprocess.run([PY, str(script), *extra], cwd=HERE).returncode
    dt = time.time() - t0
    print(f"  ⏱ {name}: {dt:.0f}с, код выхода {rc}")
    return name, rc, dt


def main() -> None:
    ap = argparse.ArgumentParser(description="Оркестратор аукционов РБ → auctions_realty.xlsx")
    ap.add_argument("--sources", help="только эти площадки (через запятую)")
    ap.add_argument("--skip", help="пропустить эти площадки (через запятую)")
    ap.add_argument("--mgcn-full", action="store_true", help="mgcn перепарсить целиком")
    ap.add_argument("--no-merge", action="store_true", help="не сводить в конце")
    cfg = ap.parse_args()

    sel = [s.strip() for s in cfg.sources.split(",")] if cfg.sources else list(SITES)
    skip = {s.strip() for s in cfg.skip.split(",")} if cfg.skip else set()
    plan = [s for s in SITES if s in sel and s not in skip]
    unknown = [s for s in sel if s not in SITES]
    if unknown:
        print(f"⚠ неизвестные площадки (игнор): {', '.join(unknown)}")

    print(f"🔨 collect_auctions | площадок: {len(plan)} → {', '.join(plan)}")
    t0 = time.time()
    results = [run_site(s, cfg.mgcn_full) for s in plan]

    if not cfg.no_merge:
        print(f"\n{'=' * 64}\n▶ merge_auctions → свод\n{'=' * 64}")
        subprocess.run([PY, str(HERE / "merge_auctions.py")], cwd=HERE)
        # встроить свод вкладкой «Аукционы» в commercial_realty.xlsx (всё в одном файле)
        try:
            import embed_auctions
            embed_auctions.embed()
        except Exception as e:  # noqa: BLE001
            print(f"   ⚠ вкладка «Аукционы» не встроена: {e}")

    ok = sum(1 for _, rc, _ in results if rc == 0)
    bad = [n for n, rc, _ in results if rc not in (0,)]
    print(f"\n{'=' * 64}")
    print(f"✅ Готово за {time.time() - t0:.0f}с: успешно {ok}/{len(results)} площадок.")
    if bad:
        print(f"   ⚠ с ошибкой/пропуск: {', '.join(bad)}")
    print("   Свод: auctions_realty.xlsx")


if __name__ == "__main__":
    main()

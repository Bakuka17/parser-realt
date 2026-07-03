"""bank_geo_collect — оркестратор ГЕО-БЛОКИРОВАННЫХ банков (⚠ ЗАПУСК БЕЗ VPN).

Беларусбанк и БНБ отвечают только белорусскому IP → их сбор отделён от collect_banks
(тот работает под VPN). Запуск (Денис, VPN OFF): ./bin/python bank_geo_collect.py
Дописывает banks_belarusbank.xlsx / banks_bnb.xlsx — дашборд подхватит после ре-экспорта.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
GEO_BANKS = ["belarusbank", "bnb"]

for name in GEO_BANKS:
    print(f"\n▶ {name}")
    rc = subprocess.run([sys.executable, "-u", str(HERE / f"{name}_bank.py")], cwd=HERE).returncode
    print(f"  {name}: код {rc}")
print("\nГотово. Включай VPN; в дашборде обнови данные (ре-экспорт).")

#!/bin/bash
# Восстановление базы после аварии 09.07.2026.
# ⚠ ЗАПУСКАТЬ БЕЗ VPN (Psiphon OFF): kufar и realt не отвечают с иностранного IP,
#   а domovita/edc/bc и телефоны kufar вообще работают только с белорусского.
# Просто закрой окно, когда допишет «ГОТОВО».
cd "$(dirname "$0")" || exit 1
LOG="logs/restore_$(date +%d.%m_%H%M).log"
mkdir -p logs

echo "=== Восстановление базы · $(date '+%d.%m.%Y %H:%M') ===" | tee "$LOG"
./bin/python doctor.py 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
read -r -p "Источники выше живы и IP белорусский? Enter — продолжить, Ctrl+C — выйти. " _

# 1. Объявления: realt/megapolis/kufar/gohome/byrealty (без --full: гео-строки останутся)
./bin/python -u collect_realty.py 2>&1 | tee -a "$LOG"
# 2. Гео-источники: domovita/edc/bc
./bin/python -u collect_geo.py 2>&1 | tee -a "$LOG"
# 3. Дубль базы (обновится, только если основа жива)
./bin/python -u snapshot_db.py 2>&1 | tee -a "$LOG"
# 4. Дашборд
./bin/python -u web/export_data.py 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
./bin/python snapshot_db.py --status 2>&1 | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "ГОТОВО. Лог: $LOG" | tee -a "$LOG"
echo "Телефоны kufar добираются отдельно: «Добор kufar.command» (тоже без VPN)." | tee -a "$LOG"
read -r -p "Enter — закрыть окно. " _

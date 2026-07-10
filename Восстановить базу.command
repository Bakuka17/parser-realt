#!/bin/bash
# Досбор базы после аварии 09.07.2026.
#
# ГДЕ ЗАПУСКАТЬ:
#   БЕЗ VPN (Psiphon OFF) — предпочтительно: соберётся ВСЁ, включая гео-источники
#     (domovita/edc/bc). С белорусского IP работает всё.
#   ПОД VPN — тоже можно: realt/kufar/gohome/byrealty листинги собираются нормально
#     (проверено doctor.py 10.07). Гео-шаг соберёт 0 и остальное не сломает.
#
# Прерывать МОЖНО в любой момент: запись атомарная (kill/свет базу не бьют),
# прогресс идёт чекпойнтами, повторный запуск продолжит с места обрыва.
# Просто закрой окно, когда допишет «ГОТОВО».
cd "$(dirname "$0")" || exit 1
LOG="logs/restore_$(date +%d.%m_%H%M).log"
mkdir -p logs

echo "=== Досбор базы · $(date '+%d.%m.%Y %H:%M') ===" | tee "$LOG"
./bin/python doctor.py 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
# при запуске не из терминала (nohup/launchd) вопрос пропускаем
if [ -t 0 ]; then
  read -r -p "Источники выше живы? Enter — продолжить, Ctrl+C — выйти. " _
fi

# 1. Объявления: realt/megapolis/kufar/gohome/byrealty.
#    БЕЗ --full (иначе сотрутся гео-строки domovita/bc — их этот оркестратор не собирает).
#    --max-pages 300: на дефолтных 100 gohome упирается в лимит и недобирает.
#    В конце сам возвращает вкладку «Аукционы» (embed_auctions).
./bin/python -u collect_realty.py --max-pages 300 2>&1 | tee -a "$LOG"
# 2. Гео-источники: domovita/edc/bc (только с белорусского IP)
./bin/python -u collect_geo.py 2>&1 | tee -a "$LOG"
# 3. Журнал телефонов: занести всё добытое (append-only, потерять нельзя)
./bin/python -u phones_log.py --dump 2>&1 | tee -a "$LOG"
# 4. Дубль базы (обновится, только если основа жива)
./bin/python -u snapshot_db.py 2>&1 | tee -a "$LOG"
# 5. Дашборд
./bin/python -u web/export_data.py 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
./bin/python snapshot_db.py --status 2>&1 | tee -a "$LOG"
./bin/python phones_log.py --status 2>&1 | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "ГОТОВО. Лог: $LOG" | tee -a "$LOG"
echo "Телефоны kufar добираются отдельно: «Добор kufar.command» (нужен белорусский IP)." | tee -a "$LOG"
if [ -t 0 ]; then read -r -p "Enter — закрыть окно. " _; fi

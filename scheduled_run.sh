#!/bin/bash
# Авто-сбор по расписанию. Запускается launchd (см. настройку ниже).
# caffeinate не даёт Mac уснуть во время прогона.
cd /Users/denis/realty_env || exit 1
export PATH="/opt/homebrew/bin:$PATH"
STAMP=$(date "+%Y-%m-%d %H:%M")
echo "===== АВТО-СБОР $STAMP =====" >> logs/scheduled.log
# 1) Основные источники (realt+megapolis+kufar), инкрементально
caffeinate -i ./bin/python collect_realty.py >> logs/scheduled.log 2>&1
# 2) Аукционы: единый оркестратор (все площадки + свод в auctions_realty.xlsx)
caffeinate -i ./bin/python collect_auctions.py >> logs/scheduled.log 2>&1
echo "===== ГОТОВО $(date '+%H:%M') =====" >> logs/scheduled.log

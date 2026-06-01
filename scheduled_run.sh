#!/bin/bash
# Авто-сбор по расписанию. Запускается launchd (см. настройку ниже).
# caffeinate не даёт Mac уснуть во время прогона.
cd /Users/denis/realty_env || exit 1
export PATH="/opt/homebrew/bin:$PATH"
STAMP=$(date "+%Y-%m-%d %H:%M")
echo "===== АВТО-СБОР $STAMP =====" >> logs/scheduled.log
# 1) Основные источники (realt+megapolis+kufar), инкрементально
caffeinate -i ./bin/python collect_realty.py >> logs/scheduled.log 2>&1
# 2) Аукционы: все *_auctions.py, затем сборка
for p in mgcn ipmtorgi torgi24 auction24 gki bks eauction deloocenka konfiskat; do
    [ -f "${p}_auctions.py" ] && caffeinate -i ./bin/python "${p}_auctions.py" >> logs/scheduled.log 2>&1
done
[ -f merge_auctions.py ] && ./bin/python merge_auctions.py >> logs/scheduled.log 2>&1
echo "===== ГОТОВО $(date '+%H:%M') =====" >> logs/scheduled.log

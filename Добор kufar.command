#!/bin/bash
# Добор телефонов kufar — ТОЛЬКО С БЕЛОРУССКИМ IP (выключи VPN/Psiphon перед запуском!)
# Chrome должен быть залогинен в kufar (cookies берутся оттуда).
#
# Шаг 1: смоук headless (25 шт.) — живая проверка, работает ли добор без окна.
# Шаг 2: порция 150 (headless, если смоук прошёл; иначе с видимым окном браузера).
# Всё пишется в logs/kufar_dobor.log — покажи его Claude после прогона.
cd "$(dirname "$0")" || exit 1
LOG="logs/kufar_dobor.log"
mkdir -p logs
echo "════════════════════════════════════════════════════════"
echo "  Добор телефонов kufar → commercial_realty.xlsx"
echo "  ⚠ ВАЖНО: VPN/Psiphon ВЫКЛЮЧЕН, Chrome залогинен в kufar"
echo "════════════════════════════════════════════════════════"
echo "[$(date '+%F %T')] === шаг 1/3: смоук headless (25 шт.) ===" | tee -a "$LOG"
./bin/python kufar_phones.py --limit 25 --headless --chrome-cookies 2>&1 | tee /tmp/kufar_smoke.log
cat /tmp/kufar_smoke.log >> "$LOG"
ok=$(grep -c '✓ +375' /tmp/kufar_smoke.log)
echo "[$(date '+%F %T')] смоук: headless раскрыл $ok из 25" | tee -a "$LOG"
if [ "$ok" -ge 15 ]; then
    echo "[$(date '+%F %T')] === шаг 2/3: headless РАБОТАЕТ → порция 150 headless ===" | tee -a "$LOG"
    ./bin/python kufar_phones.py --limit 150 --headless --chrome-cookies 2>&1 | tee -a "$LOG"
else
    echo "[$(date '+%F %T')] === шаг 2/3: headless слабый ($ok/25) → порция 150 с видимым окном ===" | tee -a "$LOG"
    echo "    (откроется окно браузера — не трогай его, оно закроется само)"
    ./bin/python kufar_phones.py --limit 150 --chrome-cookies 2>&1 | tee -a "$LOG"
fi
echo "[$(date '+%F %T')] === шаг 3/3: ре-экспорт дашборда ===" | tee -a "$LOG"
./bin/python web/export_data.py 2>&1 | tail -3 | tee -a "$LOG"
echo
echo "✅ Готово. Включай VPN и покажи Claude файл logs/kufar_dobor.log"
read -r -p "Нажми Enter, чтобы закрыть окно…"

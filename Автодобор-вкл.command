#!/bin/bash
# Включить автодобор телефонов kufar (launchd, раз в 4 часа).
cd "$(dirname "$0")" || exit 1
PLIST="$HOME/Library/LaunchAgents/com.realty.kufar-autophones.plist"
cp "com.realty.kufar-autophones.plist" "$PLIST"
launchctl unload "$PLIST" 2>/dev/null
launchctl load "$PLIST" && echo "✅ Автодобор ВКЛЮЧЁН: каждые 4 часа." || { echo "Ошибка launchctl"; exit 1; }
echo ""
echo "Важно: реально добирает только когда Psiphon ВЫКЛЮЧЕН (иначе заход пропустится)."
echo "Лог:  logs/kufar_auto.log"
echo "Совет: один раз войдите в аккаунт kufar для большего лимита:"
echo "       ./bin/python kufar_phones.py --login"
echo ""
echo "Это окно можно закрыть."

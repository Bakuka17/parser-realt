#!/bin/bash
# Выключить автодобор телефонов kufar.
PLIST="$HOME/Library/LaunchAgents/com.realty.kufar-autophones.plist"
launchctl unload "$PLIST" 2>/dev/null && echo "🛑 Автодобор ВЫКЛЮЧЕН." || echo "Автодобор и так не запущен."
rm -f "$PLIST"
echo "Это окно можно закрыть."

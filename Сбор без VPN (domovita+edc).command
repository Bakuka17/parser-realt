#!/bin/bash
# Сбор domovita.by + edc.sale — ТОЛЬКО С БЕЛОРУССКИМ IP (выключи VPN/Psiphon перед запуском!)
cd "$(dirname "$0")" || exit 1
echo "════════════════════════════════════════════════════════"
echo "  Сбор domovita.by + edc.sale → commercial_realty.xlsx"
echo "  ⚠ ВАЖНО: VPN/Psiphon должен быть ВЫКЛЮЧЕН (нужен бел. IP)"
echo "════════════════════════════════════════════════════════"
./bin/python collect_geo.py
echo
echo "✅ Готово. Можно включать VPN обратно."
read -r -p "Нажми Enter, чтобы закрыть окно…"

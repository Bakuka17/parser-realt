#!/bin/bash
# Двойной клик: обновляет данные дашборда из commercial_realty.xlsx и открывает его.
cd "$(dirname "$0")" || exit 1
echo "Обновляю данные дашборда из commercial_realty.xlsx…"
./bin/python web/export_data.py
echo "Запускаю дашборд (локальный сервер + браузер)…"
./bin/python web/server.py

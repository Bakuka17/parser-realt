#!/bin/bash
# Двойной клик = запускает RealtyApp.
# Если бинарника нет — сначала собирает (нужны Command Line Tools).
cd "$(dirname "$0")/RealtyApp" || exit 1
if [ ! -x ./.build/debug/RealtyApp ]; then
    echo "Бинарника нет, собираю..."
    swift build || { echo "Сборка не удалась"; read -n 1 -s; exit 1; }
fi
./.build/debug/RealtyApp &
echo "Приложение запущено. Окно можно закрыть."
sleep 1

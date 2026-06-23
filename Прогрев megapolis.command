#!/bin/bash
# Двойной клик: аккуратно докачивает фото megapolis в кэш (web/photos_cache/).
# megapolis протух кэш-URL фото (assets/cache/...-600x400 → 404) — сервер берёт og:image
# деталки как запасной. Но megapolis БАНИТ всплеск запросов (TCP-дроп), поэтому здесь
# медленный темп: 1 поток + пауза 4с между объектами (~1ч на ~580 объектов).
# ЛУЧШЕ запускать БЕЗ VPN (Psiphon OFF) — megapolis свой, с белорусского IP добрее.
# Если всё равно начнёт банить (подряд «без фото») — увеличьте --delay до 8.
# Идемпотентно/резюмируемо: Ctrl+C и повторный запуск продолжат с места.
cd "$(dirname "$0")" || exit 1
echo "Прогрев фото megapolis (медленно, ~1ч). Лучше без VPN."
echo "Прервать — Ctrl+C; повторный запуск продолжит."
echo
./bin/python web/prefetch_photos.py --sources megapolis-real.by --workers 1 --delay 4 --reset-none
echo
echo "Готово. Закройте окно."

#!/usr/bin/env python3
"""Прогрев фото-кэша дашборда: качает фото всех объектов в web/photos_cache/,
чтобы дашборд показывал их МГНОВЕННО (без докачки на лету при прокрутке).

Идемпотентно: уже скачанные и помеченные «без фото» пропускает — можно прерывать
(Ctrl+C) и запускать снова, продолжит с места. Переиспользует логику сервера
(полноразмер kufar gallery, og:image для realt без фото).

Запуск:
  ./bin/python web/prefetch_photos.py                       # все объекты
  ./bin/python web/prefetch_photos.py --limit 500           # порцией
  ./bin/python web/prefetch_photos.py --sources kufar.by,realt.by,megapolis-real.by
  ./bin/python web/prefetch_photos.py --workers 3           # параллельность (по умолч. 3)

Можно гнать ПОД VPN (сервер тянет небольшими пачками — kufar не стопорит) или БЕЗ
VPN (с белорусского IP быстрее). Гонит долго (тысячи фото) — нормально оставить в фоне.
"""
import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402 — переиспользуем load_index / _cached_photo / fetch_photo


def purge_orphans(items, days):
    """Удалить фото объектов, которых нет в базе. Возвращает освобождённые байты.

    Карантин `days` защищает «мигнувшее» объявление: временно пропало из выдачи —
    фото не теряем. Но после аварии 09.07 хэши сменились массово и старые объекты
    не вернутся никогда → тогда чистим принудительно (--orphan-days 0).
    """
    live = {it.get("hash") or "" for it in items}
    if len(live) <= 1000:   # гвард: не сносить кэш, если data.js пустой или битый
        print(f"⚠️  В индексе всего {len(live)} объектов — уборка пропущена (похоже на битый data.js)")
        return 0
    cutoff = time.time() - days * 86400
    freed = n = 0
    for f in server.PHOTOS_CACHE_DIR.iterdir():
        if f.stem in live:
            continue
        st = f.stat()
        if st.st_mtime >= cutoff:
            continue
        freed += st.st_size
        f.unlink()
        n += 1
    if n:
        print(f"Удалено осиротевших файлов: {n} ({freed/1024**3:.2f} ГБ) — "
              f"объектов нет в базе дольше {days} дн.")
    return freed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="макс. сколько СКАЧАТЬ за прогон (0 = все)")
    ap.add_argument("--sources", default="", help="через запятую: kufar.by,realt.by,…")
    ap.add_argument("--workers", type=int, default=3, help="параллельные загрузки (≤3 безопасно для kufar)")
    ap.add_argument("--delay", type=float, default=0.0, help="пауза между объектами, с (megapolis банит залп: --workers 1 --delay 4)")
    ap.add_argument("--reset-none", action="store_true", help="снять .none-метки выбранных --sources перед прогревом (стереть ложные негативы от бана)")
    ap.add_argument("--orphan-days", type=int, default=30, help="возраст сироты для удаления, дней (0 = чистить всех, кого нет в базе)")
    ap.add_argument("--purge-only", action="store_true", help="только уборка сирот, без прогрева")
    a = ap.parse_args()

    server.load_index()
    if not server.INDEX:
        print("⚠️  Нет данных. Сначала: ./bin/python web/export_data.py")
        return
    server.PHOTOS_CACHE_DIR.mkdir(exist_ok=True)
    srcs = {s.strip() for s in a.sources.split(",") if s.strip()}

    items = list(server.INDEX.values())
    freed = purge_orphans(items, a.orphan_days)
    if a.purge_only:
        print(f"Освобождено: {freed/1024**3:.2f} ГБ. Прогрев не запускался (--purge-only).")
        return
    if a.reset_none:   # снять негативные метки (ложные .none от бана megapolis) перед прогревом
        reset = 0
        for it in items:
            if srcs and it.get("source") not in srcs:
                continue
            f = server.PHOTOS_CACHE_DIR / ((it.get("hash") or "") + ".none")
            if f.exists():
                f.unlink()
                reset += 1
        print(f"Снято .none-меток: {reset} (будут перепроверены)")
    # что ещё не в кэше и не помечено «без фото» — только это и качаем
    def pending(it):
        h = it.get("hash") or ""
        if srcs and it.get("source") not in srcs:
            return False
        if server._cached_photo(h):
            return False
        if (server.PHOTOS_CACHE_DIR / (h + ".none")).exists():
            return False
        return bool(h)

    todo = [it for it in items if pending(it)]
    print(f"Объектов всего: {len(items)} · к загрузке: {len(todo)} "
          f"(остальное уже в кэше или без фото)")
    if a.limit:
        todo = todo[:a.limit]

    done = miss = 0
    t0 = time.time()
    lock = __import__("threading").Lock()

    def work(it):
        nonlocal done, miss
        p = server.fetch_photo(it.get("hash"))
        if a.delay:
            time.sleep(a.delay)
        with lock:
            if p:
                done += 1
            else:
                miss += 1
            n = done + miss
            if n % 50 == 0 or n == len(todo):
                rate = n / max(time.time() - t0, 0.1)
                eta = (len(todo) - n) / max(rate, 0.1)
                print(f"  {n}/{len(todo)} · скачано {done}, без фото {miss} · "
                      f"{rate:.1f}/с · осталось ~{eta/60:.0f} мин", flush=True)

    try:
        with ThreadPoolExecutor(max_workers=max(1, a.workers)) as ex:
            list(ex.map(work, todo))
    except KeyboardInterrupt:
        print("\nПрервано — прогресс сохранён, перезапуск продолжит с места.")

    have = sum(1 for it in items if server._cached_photo(it.get("hash") or ""))
    print(f"\nГотово за {(time.time()-t0)/60:.1f} мин: +{done} скачано, {miss} без фото.")
    print(f"Кэш покрывает {have}/{len(items)} объектов ({have*100//max(len(items),1)}%).")


if __name__ == "__main__":
    main()

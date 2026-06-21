"""backfill_photos — дотянуть og:image с деталок для объектов БЕЗ фото.

Парсеры берут фото из листинга; у части объектов там пусто, хотя на странице объекта
og:image есть (megapolis ~900, realt ~940). Этот скрипт заранее дотягивает og:image и
пишет в web/photo_cache.json {hash: url}; ре-экспорт (export_data) вливает их в data.js —
и фото появляются СРАЗУ во всех карточках, а не лениво при прокрутке.

  ./bin/python backfill_photos.py                         # все источники без фото
  ./bin/python backfill_photos.py --sources megapolis-real.by
  ./bin/python backfill_photos.py --workers 3             # мягче к сайтам (бан-риск)

⚠ megapolis/realt банят на всплеске — workers держим небольшим (3-4), это лёгкий GET деталки.
"""
import argparse
import json
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "web"))
import fetch_ad  # noqa: E402

DATA = ROOT / "web" / "data.js"
CACHE = ROOT / "web" / "photo_cache.json"


def load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", help="только эти источники (через запятую)")
    ap.add_argument("--workers", type=int, default=4)
    cfg = ap.parse_args()

    data = json.loads(re.search(r'window\.LISTINGS=(\[.*\]);',
                                DATA.read_text(encoding="utf-8"), re.S).group(1))
    cache = load_cache()
    srcs = set(cfg.sources.split(",")) if cfg.sources else None
    todo = [x for x in data if not x.get("photo") and x.get("url") and x.get("hash")
            and x["hash"] not in cache and (not srcs or x.get("source") in srcs)]
    print(f"объектов без фото и без кэша: {len(todo)} (workers={cfg.workers})")
    if not todo:
        print("нечего добирать."); return

    done = [0]
    lock = threading.Lock()

    def work(x):
        og = ""
        try:
            og = fetch_ad.first_og_image(x["url"]) or ""
        except Exception:
            og = ""
        with lock:
            cache[x["hash"]] = og          # "" = пробовали, фото нет (не перепроверять)
            done[0] += 1
            if done[0] % 50 == 0:
                CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                got = sum(1 for v in cache.values() if v)
                print(f"  {done[0]}/{len(todo)} (всего фото в кэше: {got})")

    with ThreadPoolExecutor(max_workers=cfg.workers) as ex:
        list(ex.map(work, todo))
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    got = sum(1 for x in todo if cache.get(x["hash"]))
    print(f"\n✅ дотянуто {got}/{len(todo)} фото → photo_cache.json")
    print("   Теперь: ./bin/python web/export_data.py  (вольёт фото в data.js)")


if __name__ == "__main__":
    main()

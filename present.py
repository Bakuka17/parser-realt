#!/usr/bin/env python3
"""present.py — оффлайн-генератор презентаций недвижимости (премиум-дизайн, БЕЗ токенов).

Делает красивую HTML-презентацию из данных объекта + ТВОИХ реальных фото (не битых, как у GLM).
Открываешь в браузере → Cmd+P → «Сохранить как PDF» — готовая презентация на печать/отправку.

  ./bin/python present.py                 # пример (объект Гикало) → present.html
  ./bin/python present.py --photos ~/Downloads/гикало   # фото из своей папки

Дизайн зашит в шаблон (тёмная премиум-тема, золото, серифы) — всегда стабильно красивый.
Фото берутся из папки (jpg/png) и встраиваются в HTML (base64) — работает офлайн, ничего не битое.
Текст пока из данных DATA ниже; позже можно генерить бесплатным GLM (delegate_to_glm) и подставлять.
"""
import argparse
import base64
import html
import mimetypes
from pathlib import Path

# ── данные объекта (потом можно тянуть из commercial_realty.xlsx или вводить) ──
DATA = {
    "title": "Аренда помещения 217 м²",
    "subtitle": "в центре Минска",
    "tagline": "ул. Гикало, 1 · метро Якуба Коласа · 20 €/м²",
    "address": "Минск, ул. Гикало, 1",
    "phone": "+375 29 677 1 776",
    "agent": "Денис",
    "price_line": "20 € / м² в месяц · НДС включён",
    "params": [  # (число, подпись)
        ("217", "м² общая площадь"),
        ("2", "уровня: 1 этаж + цоколь"),
        ("3", "отдельные входные группы"),
        ("40", "кВт электрическая мощность"),
        ("2", "парковочных места"),
        ("24/7", "режим работы"),
    ],
    "about": ("Первая линия в шаговой доступности от метро Якуба Коласа. "
              "Высокий пешеходный и авто-трафик. Два уровня для гибкого зонирования: "
              "витрина и торговый зал на первом этаже, склад/офис/сервис в цоколе. "
              "Возможна перепланировка за счёт ненесущих конструкций."),
    "formats": ["Магазин", "Салон красоты", "Офис", "Пункт выдачи",
                "Кафе / бар", "Шоурум", "Студия", "Сервис"],
}

CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
body { background:#0d0d0f; font-family: 'Helvetica Neue', Arial, sans-serif; color:#e9e6df; }
.slide { width:1280px; height:720px; margin:0 auto 24px; position:relative; overflow:hidden;
  background:#141416; padding:64px 72px; }
.serif { font-family: Georgia, 'Times New Roman', serif; }
.gold { color:#c9a86a; }
.kicker { letter-spacing:.28em; font-size:12px; color:#c9a86a; text-transform:uppercase; }
.muted { color:#8b8678; }
h1 { font-size:64px; line-height:1.05; font-weight:700; }
h2 { font-size:44px; line-height:1.1; font-weight:700; }
.rule { width:64px; height:2px; background:#c9a86a; margin:20px 0; }
.grid { display:grid; gap:14px; margin-top:28px; }
.g3 { grid-template-columns: repeat(3, 1fr); }
.g4 { grid-template-columns: repeat(4, 1fr); }
.card { background:#1c1c1f; border:1px solid #2a2a2e; border-radius:10px; padding:22px; }
.num { font-family:Georgia, serif; font-size:40px; color:#c9a86a; line-height:1; }
.cap { font-size:13px; color:#9a958a; margin-top:8px; }
.chip { background:#1c1c1f; border:1px solid #2a2a2e; border-radius:8px; padding:12px 14px;
  font-size:14px; text-align:center; }
.foot { position:absolute; left:72px; bottom:48px; right:72px; display:flex;
  justify-content:space-between; font-size:12px; letter-spacing:.1em; }
.gal { display:grid; grid-template-columns: repeat(3, 1fr); gap:12px; margin-top:24px; }
.gal img { width:100%; height:196px; object-fit:cover; border-radius:8px; display:block; }
.ph { width:100%; height:196px; border-radius:8px; background:#1c1c1f; border:1px dashed #3a3a3e;
  display:flex; align-items:center; justify-content:center; color:#5a564d; font-size:13px; }
.big { font-family:Georgia, serif; font-size:88px; color:#c9a86a; line-height:1; }
@media print { body{background:#fff;} .slide{ margin:0; page-break-after:always; } }
"""


def imgs_b64(folder: Path, limit=6):
    """Реальные фото из папки → data-URI (встраиваем, чтобы офлайн и ничего не билось)."""
    out = []
    if folder and folder.is_dir():
        for p in sorted(folder.iterdir()):
            if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
                mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
                b = base64.b64encode(p.read_bytes()).decode()
                out.append(f"data:{mime};base64,{b}")
            if len(out) >= limit:
                break
    return out


def esc(s):
    return html.escape(str(s))


def build(d: dict, photos: list) -> str:
    params = "".join(
        f'<div class="card"><div class="num">{esc(n)}</div><div class="cap">{esc(c)}</div></div>'
        for n, c in d["params"])
    gallery = "".join(f'<img src="{p}" alt="">' for p in photos) or \
        '<div class="ph">фото объекта — положи снимки в папку --photos</div>' * 3
    chips = "".join(f'<div class="chip">{esc(f)}</div>' for f in d["formats"])
    return f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<title>{esc(d['title'])}</title><style>{CSS}</style></head><body>

<section class="slide">
  <div class="kicker">Коммерческая недвижимость — аренда</div>
  <div style="margin-top:180px">
    <h1 class="serif">{esc(d['title'])}<br><span class="gold">{esc(d['subtitle'])}</span></h1>
    <div class="rule"></div>
    <div class="kicker" style="color:#9a958a">{esc(d['tagline'])}</div>
  </div>
  <div class="foot"><span class="muted">{esc(d['price_line'])}</span>
    <span class="gold">{esc(d['phone'])} · {esc(d['agent'])}</span></div>
</section>

<section class="slide">
  <div class="kicker">Параметры объекта</div>
  <h2 class="serif" style="margin-top:24px">Цифры, которые определяют формат</h2>
  <div class="grid g3">{params}</div>
</section>

<section class="slide">
  <div class="kicker">О помещении</div>
  <h2 class="serif" style="margin-top:24px">Локация и преимущества</h2>
  <p style="max-width:760px;margin-top:20px;line-height:1.7;color:#cfcabf;font-size:18px">{esc(d['about'])}</p>
  <div class="kicker" style="margin-top:36px">Подойдёт для</div>
  <div class="grid g4" style="margin-top:14px">{chips}</div>
</section>

<section class="slide">
  <div class="kicker">Галерея</div>
  <h2 class="serif" style="margin-top:24px">Помещение в деталях</h2>
  <div class="gal">{gallery}</div>
</section>

<section class="slide">
  <div class="kicker">Связаться</div>
  <div style="margin-top:150px;text-align:center">
    <h1 class="serif">Договоритесь<br><span class="gold">о просмотре</span></h1>
    <div class="rule" style="margin:24px auto"></div>
    <div class="big">{esc(d['phone'])}</div>
    <p class="muted" style="margin-top:18px">{esc(d['agent'])} · {esc(d['address'])}</p>
  </div>
</section>

</body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Оффлайн-генератор презентаций недвижимости")
    ap.add_argument("--photos", help="папка с фото объекта (jpg/png)")
    ap.add_argument("--out", default="present.html")
    cfg = ap.parse_args()
    photos = imgs_b64(Path(cfg.photos).expanduser()) if cfg.photos else []
    Path(cfg.out).write_text(build(DATA, photos), encoding="utf-8")
    print(f"✅ {cfg.out} готов ({len(photos)} фото). Открой в браузере → Cmd+P → «Сохранить как PDF».")


if __name__ == "__main__":
    main()

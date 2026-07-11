"""Мастер-иконка приложения 1024×1024 из логотипа дашборда (web/logo.png — сфера
с золотым кольцом): вписывает его в маковский скруглённый квадрат → /tmp/icon_master.png.
Дальше: sips (размеры iconset) + iconutil -c icns → AppIcon.icns."""
from pathlib import Path

from PIL import Image, ImageDraw

S = 1024
LOGO = Path(__file__).resolve().parent.parent / "web" / "logo.png"

logo = Image.open(LOGO).convert("RGBA")
m = int(S * 0.085)                      # стандартные поля маковской иконки
inner = S - 2 * m
logo = logo.resize((inner, inner), Image.LANCZOS)

mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([m, m, S - m, S - m], radius=int(S * 0.225), fill=255)

canvas = Image.new("RGBA", (S, S), (0, 0, 0, 0))
canvas.paste(logo, (m, m))
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
img.paste(canvas, (0, 0), mask)

img.save("/tmp/icon_master.png")
print("OK → /tmp/icon_master.png", img.size)

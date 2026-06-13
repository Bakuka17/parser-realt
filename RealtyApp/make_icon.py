"""Генерирует мастер-иконку 1024×1024 (зелёный фон + белые здания) → /tmp/icon_master.png."""
from PIL import Image, ImageDraw

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# --- фон: скруглённый квадрат с вертикальным зелёным градиентом ---
top, bot = (52, 168, 116), (24, 104, 74)        # светло- → тёмно-зелёный (цвет дашборда)
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
for y in range(S):
    t = y / S
    gd.line([(0, y), (S, y)],
            fill=(int(top[0]*(1-t)+bot[0]*t),
                  int(top[1]*(1-t)+bot[1]*t),
                  int(top[2]*(1-t)+bot[2]*t), 255))
m = int(S * 0.085)                               # поле по краям
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([m, m, S-m, S-m], radius=int(S*0.225), fill=255)
img.paste(grad, (0, 0), mask)

d = ImageDraw.Draw(img)
W = (255, 255, 255, 255)
win = (int((top[0]+bot[0])/2*0.7), int((top[1]+bot[1])/2*0.7), int((top[2]+bot[2])/2*0.7), 255)

def building(x0, y0, x1, y1, cols, rows):
    d.rounded_rectangle([x0, y0, x1, y1], radius=int(S*0.012), fill=W)
    # сетка окон (зелёные «вырезы»)
    pad = int((x1-x0) * 0.16)
    gx0, gy0, gx1, gy1 = x0+pad, y0+pad, x1-pad, y1-int((y1-y0)*0.06)
    cw = (gx1-gx0) / (cols*2-1)
    ch = (gy1-gy0) / (rows*2-1)
    for r in range(rows):
        for c in range(cols):
            wx = gx0 + c*2*cw
            wy = gy0 + r*2*ch
            d.rounded_rectangle([wx, wy, wx+cw, wy+ch], radius=int(cw*0.18), fill=win)

# короткое здание справа сзади, высокое слева спереди
building(int(S*0.52), int(S*0.42), int(S*0.71), int(S*0.71), cols=2, rows=4)
building(int(S*0.29), int(S*0.32), int(S*0.51), int(S*0.71), cols=3, rows=6)

img.save("/tmp/icon_master.png")
print("OK → /tmp/icon_master.png", img.size)

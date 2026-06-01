import re
with open('realty_parser_v7.py', 'r', encoding='utf-8') as f:
    s = f.read()

# 1. Переносим "НДС" из позиции после "Состояние" к "Цене за м²"
s = s.replace('"Цена за м²",\n    "Этаж',
              '"Цена за м²","НДС",\n    "Этаж')
s = s.replace('"Состояние","НДС",', '"Состояние",')

# 2. Соответственно меняем ширины колонок
s = s.replace(
    'widths = [11,28,18,12,22,18,13,10,11,14,8,10,14,12,16,16,22,38,14,12,14,18,16,18,14,14,14]',
    'widths = [11,28,18,12,22,18,8,13,10,11,14,10,14,12,16,16,22,38,14,12,14,18,16,18,14,14,14]'
)

# 3. Дата — нормализуем к ДД.ММ.ГГГГ с нулями (например "5.1.2026" -> "05.01.2026")
old = 'm = re.search(r"(\\d{1,2}\\.\\d{1,2}\\.\\d{4})", region)\n    if m: return m.group(1)'
new = 'm = re.search(r"(\\d{1,2})\\.(\\d{1,2})\\.(\\d{4})", region)\n    if m: return f"{int(m.group(1)):02d}.{int(m.group(2)):02d}.{m.group(3)}"'
s = s.replace(old, new)

# 4. В Excel — принудительно текстовый формат для колонки "Дата публикации",
#    чтобы Excel не превращал её в свою внутреннюю дату
old_cell = '''                if name == "Тип":
                    cc.fill = PatternFill("solid", fgColor=TYPE_COLORS.get(val, "888888"))'''
new_cell = '''                if name == "Дата публикации":
                    cc.number_format = "@"
                    cc.alignment = Alignment(horizontal="center", vertical="top")
                if name == "Тип":
                    cc.fill = PatternFill("solid", fgColor=TYPE_COLORS.get(val, "888888"))'''
s = s.replace(old_cell, new_cell)

with open('realty_parser_v8.py', 'w', encoding='utf-8') as f:
    f.write(s)
print("✅ realty_parser_v8.py создан")

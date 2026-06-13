from __future__ import annotations
import re

_LEADING = [
    'г.', 'гор.', 'город', 'г.п.', 'гп',
    'аг.', 'агрогородок',
    'д.', 'дер.', 'деревня',
    'п.', 'пос.', 'посёлок', 'поселок',
]

_TRAILING = ['с/с', 'с.с.', 'сельсовет']

_LEAD_RE = re.compile(
    r'^(?:' + '|'.join(re.escape(m) for m in _LEADING)
    + r'|(?:[A-Za-zА-Яа-яЁё]\s*[.]))\s*',
    re.IGNORECASE,
)


def normalize_city(raw: str | None) -> str:
    if not raw:
        return ''
    s = re.sub(r'\s+', ' ', raw).strip()

    changed = True
    while changed:
        changed = False
        m = _LEAD_RE.match(s)
        if m and m.group() != s:
            s = s[m.end():].strip()
            changed = True

    lower = s.lower()
    for t in _TRAILING:
        tl = t.lower()
        if lower.endswith(' ' + tl):
            s = s[:-(len(t) + 1)].strip()
            lower = s.lower()
        elif lower == tl:
            s = ''
            break

    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'\s+[.,;:]+$', '', s)
    s = re.sub(r'^[.,;:]+\s+', '', s)
    return s

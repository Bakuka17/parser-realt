import re
from typing import Optional


def normalize_phone(raw: str) -> Optional[str]:
    digits = re.sub(r'[^\d+]', '', raw)
    if digits.startswith('+'):
        digits = digits[1:]
    if not digits.isdigit():
        return None
    if digits.startswith('375') and len(digits) == 12:
        return '+' + digits
    if digits.startswith('80') and len(digits) == 11:
        return '+375' + digits[2:]
    return None


def normalize_phones(raw: str) -> list[str]:
    candidates = re.findall(r'[\d+\s\-().]{5,}', raw)
    seen = set()
    result = []
    for c in candidates:
        canon = normalize_phone(c)
        if canon and canon not in seen:
            seen.add(canon)
            result.append(canon)
    return result


def format_phone(canon: str) -> str:
    if len(canon) != 13 or not canon.startswith('+375'):
        raise ValueError(f'Not a valid canon: {canon}')
    return f'+375 ({canon[4:6]}) {canon[6:9]}-{canon[9:11]}-{canon[11:]}'

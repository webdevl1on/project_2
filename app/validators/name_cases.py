"""Explicit words and search keys; no gender inference or declension guesses."""
import unicodedata
from app.name_cases import SEXES


def word(value, *, required=True, maximum=100, minimum=1):
    if value is not None and not isinstance(value, str):
        raise ValueError("Слово має бути текстом.")
    value = unicodedata.normalize("NFC", value or "").strip()
    if not value:
        if required:
            raise ValueError("Заповніть слово.")
        return None
    if not minimum <= len(value) <= maximum:
        raise ValueError(f"Допустима довжина: {minimum}–{maximum} символів.")
    if (not value[0].isalpha() or not value[-1].isalpha()
            or any(not (char.isalpha() or char in "-'’ʼ‘ ‐‑") for char in value)):
        raise ValueError("Дозволені літери, апостроф, дефіс і пробіли між частинами слова.")
    return value


def search_key(value):
    value = unicodedata.normalize("NFC", value or "")
    value = value.translate(str.maketrans({char: "'" for char in "’ʼ‘"} | {char: "-" for char in "‐‑"}))
    return " ".join(value.split()).casefold()


def sex(value, *, required=True):
    if value is not None and not isinstance(value, str):
        raise ValueError("Стать має бути male або female.")
    value = (value or "").strip()
    if not value and not required:
        return None
    if value not in SEXES:
        raise ValueError("Оберіть стать: чоловіча або жіноча.")
    return value

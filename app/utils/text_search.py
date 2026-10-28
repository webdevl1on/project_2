"""Reusable parameterized Unicode substring matching for SQLite tables."""
import unicodedata
from sqlalchemy import func


def normalized_text(value):
    return ' '.join(unicodedata.normalize('NFC',str(value or '')).casefold().split())


def unicode_contains(value,needle):
    return int(normalized_text(needle) in normalized_text(value))


def contains_clause(column,text):
    text=(text or '').strip()
    if len(text)>250:raise ValueError('Містить текст: максимум 250 символів.')
    return func.unicode_contains(column,text)==1

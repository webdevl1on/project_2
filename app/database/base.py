from sqlalchemy.orm import declarative_base

Base = declarative_base()

# Every SQLite connection, including seed/test engines, enforces foreign keys.
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

@event.listens_for(Engine, "connect")
def sqlite_integrity(connection, record):
    if isinstance(connection, sqlite3.Connection):
        connection.execute("PRAGMA foreign_keys=ON")
        from app.utils.text_search import unicode_contains
        from app.geography import GEO_FIELDS,DETAIL_FIELDS
        from app.utils.address_format import format_address
        connection.create_function('unicode_contains',2,unicode_contains,deterministic=True)
        keys=(*GEO_FIELDS,'settlement_type',*DETAIL_FIELDS)
        connection.create_function('formatted_address',len(keys),lambda *values:format_address(dict(zip(keys,values))),deterministic=True)

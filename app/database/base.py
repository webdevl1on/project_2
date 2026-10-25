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

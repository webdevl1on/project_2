"""Add contacts without modifying existing records."""
import argparse
import os
from datetime import datetime, UTC
from pathlib import Path
import sqlite3
import uuid
from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateTable, CreateIndex
from app.database.base import Base
from app import models
from app.database.schema_check import required_sqlite_triggers

NEW_TABLES = (models.PersonContact.__table__,)


def columns(connection, table):
    return {row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')}


def integrity(connection):
    if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise ValueError("SQLite не пройшла перевірку цілісності; міграцію не виконано.")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise ValueError("У БД є порушення зовнішніх ключів; спочатку виправте їх окремо.")


def create_table(connection, table):
    connection.execute(str(CreateTable(table).compile(dialect=sqlite.dialect())))
    for index in table.indexes:
        connection.execute(str(CreateIndex(index).compile(dialect=sqlite.dialect())))


def _migrate(database):
    path = Path(database).resolve()
    if not path.is_file():
        raise ValueError("Вкажіть наявний файл SQLite. Нова БД цією командою не створюється.")
    with path.open("rb") as stream:
        if stream.read(16) != b"SQLite format 3\x00":
            raise ValueError("Вибраний файл не є SQLite.")
    connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, isolation_level=None)
    backup = None
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        integrity(connection)
        present = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        new_names = {table.name for table in NEW_TABLES}
        from app.database.service_schema import ADDED_COLUMNS
        from app.models.service_basis import NEW_TABLE_NAMES
        for table in Base.metadata.sorted_tables:
            from app.models.documents import NEW_TABLE_NAMES as DOCUMENT_TABLES
            if table.name in DOCUMENT_TABLES: continue
            if table.name in NEW_TABLE_NAMES: continue
            if table.name == 'person_position_mirages': continue
            if table.name in new_names:
                continue
            required = {column.name for column in table.columns}
            required -= ADDED_COLUMNS.get(table.name,set())
            if table.name not in present or not required <= columns(connection, table.name):
                raise ValueError(f"Схема {table.name} не відповідає попередній штатній архітектурі. Потрібна окрема міграція цієї БД.")
        if "person_positions" in present:
            raise ValueError("Виявлено застарілу person_positions. Ця міграція її не перетворює.")
        installed = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
        if not required_sqlite_triggers() <= installed:
            raise ValueError("Відсутні чинні тригери кадрової історії або точних дат. Потрібна окрема перевірка цієї БД.")
        for table in NEW_TABLES:
            if table.name in present and not {column.name for column in table.columns} <= columns(connection, table.name):
                raise ValueError(f"Неповна стороння таблиця {table.name}; автоматичне виправлення заборонено.")
        if 'person_contacts' in present:
            installed_indexes={row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            if not {index.name for index in models.PersonContact.__table__.indexes} <= installed_indexes:
                raise ValueError('Наявна таблиця контактів не має необхідних індексів; потрібна окрема перевірка.')
        needs_change = not new_names <= present
        if not needs_change:
            return None
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.stem}.before-contacts-{stamp}-{uuid.uuid4().hex[:8]}.sqlite3")
        # Exclusive target plus SQLite backup API keeps a consistent copy, including WAL.
        descriptor = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        target = sqlite3.connect(backup)
        try:
            connection.backup(target)
        finally:
            target.close()
        connection.execute("BEGIN IMMEDIATE")
        try:
            for table in NEW_TABLES:
                if table.name not in present:
                    create_table(connection, table)
            integrity(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        return backup
    finally:
        connection.close()


def migrate(database):
    from app.database.maintenance import database_lease
    from app.services.database_reset import check_target
    path=Path(database).absolute()
    check_target(path)
    with database_lease(path):
        return _migrate(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        backup = migrate(args.database)
    except (OSError, ValueError, sqlite3.Error) as error:
        print(f"Міграцію скасовано: {error}")
        return 2
    print(f"Міграцію завершено. Резервна копія: {backup}" if backup else "Схема вже оновлена; змін не внесено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

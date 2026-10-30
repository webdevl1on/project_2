"""Explicit additive migration, with backup, lease and transactional DDL."""
import argparse
import os
import sqlite3
import uuid
from pathlib import Path
from datetime import datetime, UTC
from app import models
from app.models.medical import NEW_TABLE_NAMES as MEDICAL_TABLES
from app.database.base import Base
from app.database.maintenance import database_lease
from app.database.migrate_contacts import columns, integrity, create_table
from app.database.schema_check import required_sqlite_triggers
from app.models.service_basis import NEW_TABLE_NAMES, install_date_guards
from app.services.database_reset import check_target


def migrate(database):
    path = Path(database).absolute()
    check_target(path)
    if not path.is_file():
        raise ValueError('Вкажіть наявну SQLite. Нова БД цією командою не створюється.')
    with path.open('rb') as stream:
        if stream.read(16) != b'SQLite format 3\x00':
            raise ValueError('Вибраний файл не є SQLite.')
    with database_lease(path):
        connection = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, isolation_level=None)
        try:
            connection.execute('PRAGMA foreign_keys=ON'); integrity(connection)
            present = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            installed = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            indexes = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            for table in Base.metadata.sorted_tables:
                if table.name in MEDICAL_TABLES: continue
                from app.models.documents import NEW_TABLE_NAMES as DOCUMENT_TABLES
                if table.name in DOCUMENT_TABLES: continue
                if table.name not in present:
                    if table.name in NEW_TABLE_NAMES: continue
                    raise ValueError(f'Немає {table.name}; спочатку виконайте попередні міграції.')
                if not {c.name for c in table.columns} <= columns(connection, table.name):
                    raise ValueError(f'Неповна структура {table.name}; автоматичне виправлення заборонено.')
                if table.name in NEW_TABLE_NAMES and not {i.name for i in table.indexes} <= indexes:
                    raise ValueError(f'Відсутні необхідні індекси {table.name}; потрібна окрема перевірка.')
            required = required_sqlite_triggers() | {'exact_assignment_orders_insert', 'exact_assignment_orders_update'}
            if not required <= installed or 'person_positions' in present:
                raise ValueError('Схема кадрової історії/тригерів не відповідає чинній. Спочатку виконайте попередні міграції.')
            guards = {'exact_service_basis_insert', 'exact_service_basis_update'}
            if NEW_TABLE_NAMES <= present and guards <= installed:
                return None
            backup = path.with_name(path.stem + '.before-service-bases-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8] + '.sqlite3')
            descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(descriptor)
            with sqlite3.connect(backup) as target:
                connection.backup(target)
            connection.execute('BEGIN IMMEDIATE')
            try:
                for table in Base.metadata.sorted_tables:
                    if table.name in MEDICAL_TABLES: continue
                    from app.models.documents import NEW_TABLE_NAMES as DOCUMENT_TABLES
                    if table.name in DOCUMENT_TABLES: continue
                    if table.name in NEW_TABLE_NAMES and table.name not in present:
                        create_table(connection, table)
                class Adapter:
                    def exec_driver_sql(self, sql): connection.execute(sql)
                install_date_guards(Adapter())
                integrity(connection)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            return backup
        finally:
            connection.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        backup = migrate(args.database)
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f'Міграцію скасовано: {error}'); return 2
    print(f'Міграцію завершено. Backup: {backup}' if backup else 'Схема вже актуальна; змін немає.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

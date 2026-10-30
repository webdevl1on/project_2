"""Explicit additive migration; no automatic changes to an existing database."""
import argparse
from datetime import datetime, UTC
from pathlib import Path
import os
import sqlite3
import uuid
from app import models
from app.database.base import Base
from app.database.maintenance import database_lease
from app.database.migrate_contacts import create_table, columns, integrity
from app.database.schema_check import required_sqlite_triggers
from app.models.documents import GUARD_NAMES as DOCUMENT_GUARDS
from app.models.medical import NEW_TABLE_NAMES, GUARDS, install_guards
from app.services.database_reset import check_target


def migrate(database):
    path=Path(database).absolute();check_target(path)
    if not path.is_file():raise ValueError('Потрібна наявна SQLite; спочатку виконайте попередні міграції.')
    with database_lease(path):
        connection=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,isolation_level=None)
        try:
            connection.execute('PRAGMA foreign_keys=ON');integrity(connection)
            present={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            installed={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            indexes={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            for table in Base.metadata.sorted_tables:
                if table.name in NEW_TABLE_NAMES:continue
                if table.name not in present or not {c.name for c in table.columns}<=columns(connection,table.name):raise ValueError('Неповна попередня схема: '+table.name)
            required=required_sqlite_triggers()|DOCUMENT_GUARDS|{'exact_assignment_orders_insert','exact_assignment_orders_update','exact_service_basis_insert','exact_service_basis_update'}
            if not required<=installed:raise ValueError('Відсутні захисні тригери попередньої схеми.')
            if NEW_TABLE_NAMES & present:
                if not NEW_TABLE_NAMES<=present:raise ValueError('Неповна медична схема; автоматичне виправлення заборонено.')
                for name in NEW_TABLE_NAMES:
                    table=Base.metadata.tables[name]
                    if not {c.name for c in table.columns}<=columns(connection,name) or not {i.name for i in table.indexes}<=indexes:raise ValueError('Неповна таблиця/індекси: '+name)
                if not GUARDS<=installed:raise ValueError('Відсутні захисні тригери модуля.')
                return None
            backup=path.with_name(path.stem+'.before-medical-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.sqlite3')
            fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            with sqlite3.connect(backup) as target:connection.backup(target)
            connection.execute('BEGIN IMMEDIATE')
            try:
                for table in Base.metadata.sorted_tables:
                    if table.name in NEW_TABLE_NAMES:create_table(connection,table)
                class Adapter:
                    def exec_driver_sql(self,sql):connection.execute(sql)
                install_guards(Adapter());integrity(connection);connection.commit()
            except Exception:connection.rollback();raise
            return backup
        finally:connection.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',required=True,type=Path)
    try:backup=migrate(parser.parse_args(argv).database)
    except (ValueError,OSError,sqlite3.Error) as error:print(f'Міграцію скасовано: {error}');return 2
    print(f'Міграцію виконано; backup: {backup}' if backup else 'Схема вже актуальна.');return 0

if __name__=='__main__':raise SystemExit(main())

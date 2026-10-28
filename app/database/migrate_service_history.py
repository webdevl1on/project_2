"""Explicit additive migration: tokens, assignment orders, historical periods and mirages."""
import argparse,os,sqlite3,uuid
from pathlib import Path
from datetime import datetime,UTC
from sqlalchemy.schema import CreateColumn,CreateTable,CreateIndex
from sqlalchemy.dialects import sqlite
from app import models
from app.database.base import Base
from app.database.service_schema import ADDED_COLUMNS,install_order_guards
from app.database.migrate_geography import columns,integrity
from app.database.schema_check import required_sqlite_triggers
from app.database.maintenance import database_lease
from app.services.database_reset import check_target


def migrate(database):
    path=Path(database).absolute();check_target(path)
    if not path.is_file():raise ValueError('Вкажіть наявну SQLite.')
    with database_lease(path):
        connection=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,isolation_level=None)
        try:
            connection.execute('PRAGMA foreign_keys=ON');integrity(connection)
            tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            from app.models.service_basis import NEW_TABLE_NAMES
            for table in Base.metadata.sorted_tables:
                if table.name in NEW_TABLE_NAMES: continue
                if table.name=='person_position_mirages':continue
                required={c.name for c in table.columns}-ADDED_COLUMNS.get(table.name,set())
                if table.name not in tables or not required<=columns(connection,table.name):raise ValueError(f'Попередня схема {table.name} неповна; спочатку виконайте попередні міграції.')
            triggers={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            if not required_sqlite_triggers()<=triggers:raise ValueError('Немає чинних кадрових/точних тригерів.')
            missing={table:{name for name in names if name not in columns(connection,table)} for table,names in ADDED_COLUMNS.items()}
            if 'person_position_mirages' in tables:
                expected={c.name for c in models.PersonPositionMirage.__table__.columns}
                if not expected<=columns(connection,'person_position_mirages'):raise ValueError('Наявна таблиця Міражів має сторонню неповну структуру.')
            extra={'exact_assignment_orders_insert','exact_assignment_orders_update'}
            if not any(missing.values()) and 'person_position_mirages' in tables and extra<=triggers:return None
            backup=path.with_name(path.stem+'.before-service-history-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.sqlite3')
            fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            with sqlite3.connect(backup) as target:connection.backup(target)
            connection.execute('BEGIN IMMEDIATE')
            try:
                for table,names in missing.items():
                    for name in sorted(names):
                        column=Base.metadata.tables[table].c[name]
                        ddl=str(CreateColumn(column).compile(dialect=sqlite.dialect()))
                        if table=='person_service_history' and name=='revision':ddl+=' DEFAULT 1'
                        connection.execute(f'ALTER TABLE "{table}" ADD COLUMN {ddl}')
                table=models.PersonPositionMirage.__table__
                if table.name not in tables:
                    connection.execute(str(CreateTable(table).compile(dialect=sqlite.dialect())))
                    for index in table.indexes:connection.execute(str(CreateIndex(index).compile(dialect=sqlite.dialect())))
                # Adapter uses the same exact SQL as fresh schema creation; no existing trigger is dropped.
                class Adapter:
                    def exec_driver_sql(self,sql):connection.execute(sql)
                install_order_guards(Adapter());integrity(connection);connection.commit()
            except Exception:connection.rollback();raise
            return backup
        finally:connection.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',type=Path,required=True);args=parser.parse_args(argv)
    try:backup=migrate(args.database)
    except (OSError,ValueError,sqlite3.Error) as error:print(f'Міграцію скасовано: {error}');return 2
    print(f'Міграцію завершено; backup: {backup}' if backup else 'Схема вже актуальна.');return 0

if __name__=='__main__':raise SystemExit(main())

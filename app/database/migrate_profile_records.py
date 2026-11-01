"""Explicit additive migration of education, family and personal directives only."""
import argparse
from datetime import datetime, UTC
from pathlib import Path
import os
import re
import sqlite3
import uuid
from app import models
from app.database.base import Base
from app.database.maintenance import database_lease
from app.database.migrate_contacts import create_table, columns, integrity
from app.database.schema_check import required_sqlite_triggers
from app.models.documents import GUARD_NAMES
from app.models.medical import GUARDS
from app.models.profile_records import NEW_TABLE_NAMES
from app.services.database_reset import check_target


def _verify_added(connection):
    """Do not accept a partial/foreign lookalike table on a repeated invocation."""
    def schema(db):
        return {name: re.sub(r'\s+', ' ', sql.strip()).casefold()
                for name, sql in db.execute("SELECT name,sql FROM sqlite_master WHERE tbl_name IN (?,?,?) AND sql IS NOT NULL", tuple(sorted(NEW_TABLE_NAMES)))}
    with sqlite3.connect(':memory:') as expected:
        for name in sorted(NEW_TABLE_NAMES):
            create_table(expected, Base.metadata.tables[name])
        if schema(connection) != schema(expected):
            raise ValueError('Неповна або несумісна схема додаткових записів; автоматичне виправлення заборонено.')


def migrate(database):
    path=Path(database).resolve()
    check_target(path)
    if not path.is_file():
        raise ValueError('Вкажіть наявну SQLite з актуальною попередньою схемою.')
    with database_lease(path):
        db=sqlite3.connect(path.as_uri()+'?mode=rw', uri=True, isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys=ON')
            integrity(db)
            present={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'person_positions' in present:
                raise ValueError('Застаріла фізична person_positions потребує окремої міграції.')
            for table in Base.metadata.sorted_tables:
                if table.name in NEW_TABLE_NAMES:
                    continue
                if table.name not in present or not {c.name for c in table.columns} <= columns(db,table.name):
                    raise ValueError('Неповна попередня схема: '+table.name)
            installed={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            required=required_sqlite_triggers() | GUARD_NAMES | GUARDS | {'exact_assignment_orders_insert','exact_assignment_orders_update','exact_service_basis_insert','exact_service_basis_update'}
            if not required <= installed:
                raise ValueError('Відсутні захисні тригери попередньої схеми.')
            indexes={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            required_indexes={i.name for t in Base.metadata.sorted_tables if t.name not in NEW_TABLE_NAMES for i in t.indexes}
            if not required_indexes <= indexes:
                raise ValueError('Відсутні індекси попередньої схеми.')
            if present & NEW_TABLE_NAMES:
                if not NEW_TABLE_NAMES <= present:
                    raise ValueError('Додаткові таблиці присутні частково; міграцію скасовано.')
                _verify_added(db)
                return None
            backup=path.with_name(path.stem+'.before-profile-records-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.sqlite3')
            descriptor=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
            os.close(descriptor)
            with sqlite3.connect(backup) as target:
                db.backup(target)
            db.execute('BEGIN IMMEDIATE')
            try:
                for table in Base.metadata.sorted_tables:
                    if table.name in NEW_TABLE_NAMES:
                        create_table(db,table)
                _verify_added(db)
                integrity(db)
                db.commit()
            except Exception:
                db.rollback()
                raise
            return backup
        finally:
            db.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,type=Path)
    try:
        backup=migrate(parser.parse_args(argv).database)
    except (ValueError,OSError,sqlite3.Error) as error:
        print(f'Міграцію скасовано: {error}')
        return 2
    print(f'Міграцію виконано; backup: {backup}' if backup else 'Схема вже актуальна.')
    return 0


if __name__=='__main__':
    raise SystemExit(main())

"""Explicit index-only migration for one VLK task per injury. No data backfill."""
import argparse
from datetime import datetime,UTC
import os
from pathlib import Path
import sqlite3
import uuid
from app.database.maintenance import database_lease
from app.database.migrate_contacts import integrity,columns
from app.database.base import Base
from app import models
from app.services.database_reset import check_target

INDEX='one_injury_vlk_task'
SQL="CREATE UNIQUE INDEX one_injury_vlk_task ON personnel_tasks (injury_id) WHERE kind='injury_vlk'"


def install_index(db):db.execute(SQL)


def migrate(database):
    path=Path(database).resolve();check_target(path)
    if not path.is_file():raise ValueError('Потрібна наявна актуальна SQLite медичного модуля.')
    with database_lease(path):
        db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys=ON');integrity(db)
            for table in Base.metadata.sorted_tables:
                if not {c.name for c in table.columns}<=columns(db,table.name):raise ValueError('Попередня схема неповна: '+table.name)
            from app.models.medical import GUARDS
            from app.models.documents import GUARD_NAMES
            from app.database.schema_check import required_sqlite_triggers
            required=GUARDS|GUARD_NAMES|required_sqlite_triggers()|{'exact_assignment_orders_insert','exact_assignment_orders_update','exact_service_basis_insert','exact_service_basis_update'}
            installed={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            if not required<=installed:raise ValueError('Попередня схема не має необхідних захисних тригерів.')
            existing=db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?",(INDEX,)).fetchone()
            if existing:
                # Reject an unrelated or non-unique index bearing the expected name.
                normalize=lambda sql:''.join(sql.lower().split()).replace('"','')
                if normalize(existing[0])!=normalize(SQL):raise ValueError('Індекс має невідому структуру; автоматична заміна заборонена.')
                return None
            if db.execute("SELECT 1 FROM personnel_tasks WHERE kind='injury_vlk' GROUP BY injury_id HAVING count(*)>1").fetchone():raise ValueError('Є дублікати завдань injury_vlk. Спочатку виправте їх окремо.')
            backup=path.with_name(path.stem+'.before-injury-vlk-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.sqlite3')
            fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            with sqlite3.connect(backup) as target:db.backup(target)
            db.execute('BEGIN IMMEDIATE')
            try:install_index(db);integrity(db);db.commit()
            except Exception:db.rollback();raise
            return backup
        finally:db.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',required=True)
    try:backup=migrate(parser.parse_args(argv).database)
    except (ValueError,OSError,sqlite3.Error) as error:print(f'Міграцію скасовано: {error}');return 2
    print(f'Індекс створено; backup: {backup}' if backup else 'Індекс уже актуальний.');return 0

if __name__=='__main__':raise SystemExit(main())

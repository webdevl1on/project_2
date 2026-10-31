"""Explicit VLK workflow evolution: preserve IDs, dates, links and legacy contents."""
import argparse
from datetime import datetime,UTC
import os
from pathlib import Path
import sqlite3
import uuid
from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateTable,CreateIndex
from app import models
from app.database.base import Base
from app.database.maintenance import database_lease
from app.database.migrate_contacts import integrity,columns
from app.models.medical import install_guards,GUARDS
from app.services.database_reset import check_target

ADDED={'person_medical_exams':{'ended_on','interrupted_on','interruption_reason'},'personnel_tasks':{'exam_id'}}


def upgrade(db):
    triggers=db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
    for name,_ in triggers:db.execute('DROP TRIGGER "'+name.replace('"','""')+'"')
    table=Base.metadata.tables['person_medical_exams']
    old=columns(db,table.name)
    original_indexes=db.execute("SELECT name,sql FROM sqlite_master WHERE type='index' AND tbl_name='person_medical_exams' AND sql IS NOT NULL").fetchall()
    sql=str(CreateTable(table).compile(dialect=sqlite.dialect())).replace('CREATE TABLE person_medical_exams','CREATE TABLE _vlk_exams_new',1)
    db.execute(sql)
    names=','.join('"'+c.name+'"' for c in table.columns if c.name in old)
    db.execute(f'INSERT INTO _vlk_exams_new ({names}) SELECT {names} FROM person_medical_exams')
    db.execute('DROP TABLE person_medical_exams')
    db.execute('ALTER TABLE _vlk_exams_new RENAME TO person_medical_exams')
    for index in table.indexes:db.execute(str(CreateIndex(index).compile(dialect=sqlite.dialect())))
    for name,sql in original_indexes:
        if name not in {i.name for i in table.indexes}:db.execute(sql)
    db.execute('ALTER TABLE personnel_tasks ADD COLUMN exam_id INTEGER REFERENCES person_medical_exams(id)')
    for index in Base.metadata.tables['personnel_tasks'].indexes:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",(index.name,)).fetchone():db.execute(str(CreateIndex(index).compile(dialect=sqlite.dialect())))
    # Original unrelated guards are restored byte-for-byte. Medical definitions evolve.
    for name,sql in triggers:
        if name not in GUARDS:db.execute(sql)
    class Adapter:
        def exec_driver_sql(self,sql):db.execute(sql)
    install_guards(Adapter())


def migrate(database):
    path=Path(database).resolve();check_target(path)
    if not path.is_file():raise ValueError('Вкажіть наявну SQLite медичного модуля.')
    with database_lease(path):
        db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys=ON');integrity(db)
            present={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for table in Base.metadata.sorted_tables:
                if table.name not in present or not {c.name for c in table.columns}-ADDED.get(table.name,set()) <= columns(db,table.name):raise ValueError('Неповна попередня схема: '+table.name)
            found={t:columns(db,t)&added for t,added in ADDED.items()}
            for t,added in ADDED.items():
                allowed={c.name for c in Base.metadata.tables[t].columns}
                if columns(db,t)-allowed:raise ValueError('Невідомі додаткові колонки; їх автоматичне перенесення не погоджено: '+t)
            if any(found.values()):
                if found!=ADDED:raise ValueError('Невідома часткова схема ВЛК; автоматичне виправлення заборонено.')
                ddl=db.execute("SELECT sql FROM sqlite_master WHERE name='person_medical_exams'").fetchone()[0]
                if 'INTERRUPTED' not in ddl or not any(r[2]=='person_medical_exams' and r[3]=='exam_id' for r in db.execute('PRAGMA foreign_key_list(personnel_tasks)')):raise ValueError('Невідомі обмеження статусу або зв’язку ВЛК.')
                from app.database.schema_check import require_current_schema
                from sqlalchemy import create_engine
                engine=create_engine('sqlite:///'+str(path))
                try:require_current_schema(engine)
                finally:engine.dispose()
                return None
            installed={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            from app.models.documents import GUARD_NAMES
            from app.database.schema_check import required_sqlite_triggers
            required=(GUARDS-{'medical_exam_no_new_interrupted','medical_exam_interrupted_history'})|GUARD_NAMES|required_sqlite_triggers()
            if not required<=installed:raise ValueError('Немає необхідних попередніх захисних тригерів.')
            backup=path.with_name(path.stem+'.before-vlk-workflow-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.sqlite3')
            fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            with sqlite3.connect(backup) as target:db.backup(target)
            db.execute('PRAGMA foreign_keys=OFF');db.execute('BEGIN IMMEDIATE')
            try:upgrade(db);integrity(db);db.commit()
            except Exception:db.rollback();raise
            finally:db.execute('PRAGMA foreign_keys=ON')
            return backup
        finally:db.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',required=True)
    try:backup=migrate(parser.parse_args(argv).database)
    except (ValueError,OSError,sqlite3.Error) as error:print(f'Міграцію скасовано: {error}');return 2
    print(f'Схему оновлено; backup: {backup}' if backup else 'Схема вже актуальна.');return 0

if __name__=='__main__':raise SystemExit(main())

"""Explicit additive file order migration; originals and existing audit remain untouched."""
import argparse
from pathlib import Path
from datetime import datetime, UTC
import os
import sqlite3
import uuid
from app import models
from app.database.base import Base
from app.database.maintenance import database_lease
from app.database.migrate_contacts import integrity, columns
from app.services.database_reset import check_target


def migrate(database):
    path=Path(database).resolve();check_target(path)
    if not path.is_file():raise ValueError('Потрібна наявна актуальна SQLite.')
    with database_lease(path):
        db=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,isolation_level=None)
        try:
            db.execute('PRAGMA foreign_keys=ON');integrity(db)
            for table in Base.metadata.sorted_tables:
                expected={c.name for c in table.columns}-{ 'sort_order' } if table.name=='document_files' else {c.name for c in table.columns}
                if not expected<=columns(db,table.name):raise ValueError('Неповна попередня схема: '+table.name)
            from app.database.schema_check import required_sqlite_triggers
            from app.models.documents import GUARD_NAMES
            from app.models.medical import GUARDS
            required=required_sqlite_triggers()|GUARD_NAMES|GUARDS|{'exact_assignment_orders_insert','exact_assignment_orders_update','exact_service_basis_insert','exact_service_basis_update'}
            if not required<={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}:raise ValueError('Відсутні попередні захисні тригери.')
            indexes={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            required_indexes={i.name for t in Base.metadata.sorted_tables for i in t.indexes if i.name!='document_file_order'}
            if not required_indexes<=indexes:raise ValueError('Відсутні індекси попередньої схеми.')
            if 'sort_order' in columns(db,'document_files'):
                if 'document_file_order' not in indexes or [r[2] for r in db.execute('PRAGMA index_info(document_file_order)')]!=['document_id','sort_order','id']:raise ValueError('Неповна схема порядку копій.')
                info=next(r for r in db.execute('PRAGMA table_info(document_files)') if r[1]=='sort_order')
                if info[2].upper()!='INTEGER' or not info[3] or db.execute('SELECT 1 FROM document_files WHERE sort_order<0 OR sort_order IS NULL').fetchone():raise ValueError('Некоректна схема/дані порядку копій.')
                return None
            backup=path.with_name(path.stem+'.before-file-order-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.sqlite3')
            fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            with sqlite3.connect(backup) as target:db.backup(target)
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('ALTER TABLE document_files ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0 CHECK(sort_order >= 0)')
                db.execute('UPDATE document_files SET sort_order=(SELECT count(*) FROM document_files f WHERE f.document_id=document_files.document_id AND f.id<=document_files.id)')
                db.execute('CREATE INDEX document_file_order ON document_files(document_id,sort_order,id)')
                integrity(db);db.commit()
            except Exception:db.rollback();raise
            return backup
        finally:db.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',required=True,type=Path)
    try:backup=migrate(parser.parse_args(argv).database)
    except (ValueError,OSError,sqlite3.Error) as error:print(f'Міграцію скасовано: {error}');return 2
    print(f'Міграцію виконано; backup: {backup}' if backup else 'Схема вже актуальна.');return 0

if __name__=='__main__':raise SystemExit(main())

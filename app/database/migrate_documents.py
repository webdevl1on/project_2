"""Explicit, additive document/accounts migration; never invoked on startup."""
import argparse
from datetime import datetime, UTC
import json
import os
from pathlib import Path
import sqlite3
import uuid
from app import models
from app.database.base import Base
from app.database.maintenance import database_lease
from app.database.migrate_contacts import create_table, columns, integrity
from app.database.schema_check import required_sqlite_triggers
from app.models.documents import NEW_TABLE_NAMES, GUARD_NAMES, install_guards
from app.services.database_reset import check_target
from app.document_schemas import SCHEMAS


GUARDS=GUARD_NAMES


def _populate(connection):
    now=datetime.now(UTC).replace(tzinfo=None).isoformat(sep=' ')
    for code,(name,primary,_) in SCHEMAS.items():
        connection.execute('INSERT INTO document_types (code,name,is_primary,schema_key,is_active,created_at,updated_at,revision) VALUES (?,?,?,?,1,?,?,1)',(code,name,primary,code,now,now))
    types=dict(connection.execute('SELECT code,id FROM document_types'))
    rows=connection.execute('SELECT passport_id,person_id,is_active FROM passports ORDER BY passport_id').fetchall()
    active={}
    for _,pid,is_active in rows:
        if is_active:active[pid]=active.get(pid,0)+1
    for passport_id,pid,is_active in rows:
        current=bool(is_active and active.get(pid)==1)
        cursor=connection.execute('INSERT INTO person_documents (person_id,document_type_id,is_current,passport_id,created_at,updated_at,revision) VALUES (?,?,?,?,?,?,1)',(pid,types['passport'],current,passport_id,now,now))
        _migration_audit(connection,pid,cursor.lastrowid,types['passport'],now,{'source':'passports','passport_id':passport_id,'ambiguous_current':active.get(pid,0)>1})
    for (pid,) in connection.execute("SELECT person_id FROM persons WHERE tax_number IS NOT NULL AND trim(tax_number)!=''").fetchall():
        cursor=connection.execute('INSERT INTO person_documents (person_id,document_type_id,is_current,created_at,updated_at,revision) VALUES (?,?,1,?,?,1)',(pid,types['tax_number'],now,now))
        _migration_audit(connection,pid,cursor.lastrowid,types['tax_number'],now,{'source':'persons.tax_number'})


def _migration_audit(connection,pid,document_id,type_id,now,changes):
    connection.execute("INSERT INTO document_audit (person_id,document_id,document_type_id,actor_kind,occurred_at,operation,changes) VALUES (?,?,?,'migration',?,'migration',?)",(pid,document_id,type_id,now,json.dumps(changes)))


def migrate(database):
    path=Path(database).absolute();check_target(path)
    if not path.is_file():raise ValueError('Потрібна наявна SQLite попередньої схеми.')
    with database_lease(path):
        connection=sqlite3.connect(path.as_uri()+'?mode=rw',uri=True,isolation_level=None)
        try:
            connection.execute('PRAGMA foreign_keys=ON');integrity(connection)
            present={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            installed={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
            for table in Base.metadata.sorted_tables:
                if table.name in NEW_TABLE_NAMES:continue
                if table.name not in present or not {c.name for c in table.columns}<=columns(connection,table.name):
                    raise ValueError(f'Попередня схема {table.name} неповна; спочатку виконайте попередні міграції.')
            required=required_sqlite_triggers()|{'exact_assignment_orders_insert','exact_assignment_orders_update','exact_service_basis_insert','exact_service_basis_update'}
            if not required<=installed or 'person_positions' in present:raise ValueError('Немає актуальних кадрових/календарних тригерів.')
            if NEW_TABLE_NAMES & present:
                if not NEW_TABLE_NAMES<=present:raise ValueError('Неповна стороння схема документів; автоматичне виправлення заборонене.')
                indexes={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='index'")}
                for name in NEW_TABLE_NAMES:
                    table=Base.metadata.tables[name]
                    if not {c.name for c in table.columns}<=columns(connection,name) or not {i.name for i in table.indexes}<=indexes:
                        raise ValueError(f'Неповна таблиця/індекси {name}.')
                if not GUARDS<=installed:raise ValueError('Немає захисних тригерів документів.')
                if not set(SCHEMAS)<=set(r[0] for r in connection.execute('SELECT code FROM document_types')):raise ValueError('Неповний довідник типів документів.')
                return None
            backup=path.with_name(path.stem+'.before-documents-'+datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]+'.sqlite3')
            fd=os.open(backup,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
            with sqlite3.connect(backup) as target:connection.backup(target)
            connection.execute('BEGIN IMMEDIATE')
            try:
                for table in Base.metadata.sorted_tables:
                    if table.name in NEW_TABLE_NAMES:create_table(connection,table)
                class Adapter:
                    def exec_driver_sql(self,sql):connection.execute(sql)
                install_guards(Adapter());_populate(connection);integrity(connection);connection.commit()
            except Exception:connection.rollback();raise
            return backup
        finally:connection.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',type=Path,required=True)
    args=parser.parse_args(argv)
    try:backup=migrate(args.database)
    except (ValueError,OSError,sqlite3.Error) as error:print(f'Міграцію скасовано: {error}');return 2
    print(f'Міграцію завершено; backup: {backup}' if backup else 'Схема вже актуальна.')
    return 0


if __name__=='__main__':raise SystemExit(main())

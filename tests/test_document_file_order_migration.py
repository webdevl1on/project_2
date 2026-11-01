import sqlite3
import pytest
from sqlalchemy import create_engine, MetaData
from app.database.base import Base
from app.models import DocumentFile
from app.database import migrate_document_file_order as migration


def previous(tmp_path):
    path=tmp_path/'previous.sqlite3';engine=create_engine('sqlite:///'+str(path))
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name!='document_files'])
    metadata=MetaData()
    for t in Base.metadata.sorted_tables:t.to_metadata(metadata)
    table=metadata.tables['document_files']
    table.indexes={i for i in table.indexes if i.name!='document_file_order'}
    table.constraints={c for c in table.constraints if 'sort_order' not in str(c)}
    table._columns.remove(table.c.sort_order)
    table.create(engine);engine.dispose()
    return path


def test_additive_backup_noop_and_unchanged_original_metadata(tmp_path):
    path=previous(tmp_path)
    with sqlite3.connect(path) as db:
        # Synthetic legacy rows; seed dependencies explicitly, preserving foreign keys.
        db.execute("INSERT INTO persons(person_id) VALUES (99)")
        kind=db.execute("SELECT id FROM document_types WHERE code='other'").fetchone()[0]
        db.execute("INSERT INTO person_documents(id,person_id,document_type_id,is_current,revision,created_at,updated_at) VALUES(99,99,?,1,1,'2026-01-01','2026-01-01')",(kind,))
        for i,side in [(10,'front'),(20,'back')]:
            db.execute("INSERT INTO document_files(id,document_id,storage_key,original_name,content_type,size,sha256,side,is_removed,revision,created_at,updated_at) VALUES(?,99,?,?,?,1,?,?,?,1,'2026-01-01','2026-01-01')",(i,str(i)*32,f'{i}.pdf','application/pdf','a'*64,side,i==20))
        old=db.execute('SELECT * FROM document_files').fetchall()
    backup=migration.migrate(path);assert backup.is_file()
    with sqlite3.connect(backup) as db:assert db.execute('SELECT * FROM document_files').fetchall()==old
    with sqlite3.connect(path) as db:
        assert [r[0] for r in db.execute('SELECT sort_order FROM document_files ORDER BY id')]==[1,2]
        assert [r[:-1] for r in db.execute('SELECT * FROM document_files ORDER BY id')]==old
        assert db.execute('SELECT side,is_removed FROM document_files ORDER BY id').fetchall()==[('front',0),('back',1)]
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert migration.migrate(path) is None


def test_migration_ddl_rollback_and_incomplete_previous_schema(tmp_path,monkeypatch):
    path=previous(tmp_path);original=migration.integrity;calls=[]
    def fail(db):
        calls.append(1)
        if len(calls)==2:raise ValueError('synthetic failure')
        return original(db)
    monkeypatch.setattr(migration,'integrity',fail)
    with pytest.raises(ValueError):migration.migrate(path)
    with sqlite3.connect(path) as db:assert 'sort_order' not in {r[1] for r in db.execute('PRAGMA table_info(document_files)')}
    assert list(tmp_path.glob('*.before-file-order-*.sqlite3'))

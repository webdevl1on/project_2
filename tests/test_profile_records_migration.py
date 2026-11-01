"""Migration exercises only temporary files, including failure rollback."""
import sqlite3
import pytest
from sqlalchemy import create_engine
from app.database.base import Base
from app.database.schema_check import require_current_schema
from app.database import migrate_profile_records as migration
from app.models.profile_records import NEW_TABLE_NAMES
from app.models import Person


def prior_database(tmp_path):
    path=tmp_path/'prior.sqlite3'
    engine=create_engine('sqlite:///'+str(path))
    # Simulate the immediately preceding schema, retaining every existing guard.
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name not in NEW_TABLE_NAMES])
    with engine.begin() as db:
        db.execute(Person.__table__.insert().values(tax_number='0000000123'))
    engine.dispose()
    return path


def test_migration_backup_only_three_tables_preserves_data_and_is_repeatable(tmp_path):
    path=prior_database(tmp_path)
    with sqlite3.connect(path) as db:
        schema=db.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()
        before=db.execute('SELECT * FROM persons').fetchall()
    backup=migration.migrate(path)
    assert backup and backup.is_file()
    with sqlite3.connect(backup) as db:
        assert db.execute("SELECT name,sql FROM sqlite_master ORDER BY name").fetchall()==schema
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM persons').fetchall()==before
        assert db.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        current=dict(db.execute('SELECT name,sql FROM sqlite_master').fetchall())
        assert all(current[name]==sql for name,sql in schema)
    assert migration.migrate(path) is None
    assert len(list(tmp_path.glob('*.before-profile-records-*.sqlite3')))==1
    engine=create_engine('sqlite:///'+str(path))
    try:require_current_schema(engine)
    finally:engine.dispose()


def test_migration_rolls_back_ddl_and_keeps_backup_on_failure(tmp_path,monkeypatch):
    path=prior_database(tmp_path)
    original=migration.create_table
    def fail_after_create(db,table):
        original(db,table)
        raise sqlite3.OperationalError('synthetic failure')
    monkeypatch.setattr(migration,'create_table',fail_after_create)
    with pytest.raises(sqlite3.OperationalError,match='synthetic failure'):migration.migrate(path)
    with sqlite3.connect(path) as db:
        assert not NEW_TABLE_NAMES & {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert db.execute('SELECT tax_number FROM persons').fetchone()[0]=='0000000123'
    assert len(list(tmp_path.glob('*.before-profile-records-*.sqlite3')))==1


@pytest.mark.parametrize('damage',['prior_column','prior_guard','prior_index','partial_new','wrong_new'])
def test_migration_rejects_incomplete_or_foreign_schemas_without_writes(tmp_path,damage):
    path=prior_database(tmp_path)
    with sqlite3.connect(path) as db:
        if damage=='prior_column':db.execute('ALTER TABLE persons RENAME COLUMN tax_number TO wrong_tax')
        elif damage=='prior_guard':db.execute('DROP TRIGGER document_audit_no_delete')
        elif damage=='prior_index':db.execute('DROP INDEX one_exam_control_task')
        elif damage=='partial_new':db.execute('CREATE TABLE person_education (id INTEGER)')
        else:
            for name in NEW_TABLE_NAMES:db.execute(f'CREATE TABLE {name} (id INTEGER)')
    before=path.read_bytes()
    with pytest.raises(ValueError):migration.migrate(path)
    assert path.read_bytes()==before
    assert not list(tmp_path.glob('*.before-profile-records-*.sqlite3'))


def test_schema_checker_reports_explicit_command_and_fresh_registry_works(tmp_path):
    path=prior_database(tmp_path)
    engine=create_engine('sqlite:///'+str(path))
    try:
        with pytest.raises(ValueError,match='migrate_profile_records'):require_current_schema(engine)
    finally:engine.dispose()
    fresh=create_engine('sqlite:///'+str(tmp_path/'fresh.sqlite3'))
    try:
        Base.metadata.create_all(fresh)
        require_current_schema(fresh)
    finally:fresh.dispose()

"""Additive migration against a populated copy of the pre-feature SQLite schema."""
import sqlite3
from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.base import Base
from app.database import migrate_name_cases as migration
from app.database.schema_check import require_current_schema
from app.models import EventType, PersonEvent
from app.services.staff_service import StaffService
from tests.test_staff_history import setup


@pytest.fixture
def old_database(tmp_path):
    path = tmp_path / "existing.sqlite3"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        _, versions, positions, people = setup(db)
        person_id = people[0].person_id; position_id = positions[0].position_id
        StaffService.create_assignment(db, person_id, position_id, date(2026, 1, 1), date(2026, 5, 31))
        kind = EventType(event_type="test", event_name="Синтетична подія")
        db.add(kind); db.flush()
        db.add(PersonEvent(person_id=person_id, event_type_id=kind.event_type_id,
                           date_start=date(2025, 2, 1), date_end=None, note="Незалежна подія"))
        db.commit()
    engine.dispose()
    with sqlite3.connect(path) as db:
        for table in reversed(migration.NEW_TABLES):
            db.execute(f'DROP TABLE "{table.name}"')
        db.execute("ALTER TABLE persons DROP COLUMN sex")
    return path


def snapshot(path):
    with sqlite3.connect(path) as db:
        tables = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        rows = {name: db.execute(f'SELECT * FROM "{name}" ORDER BY rowid').fetchall() for name in tables}
        triggers = db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
    return rows, triggers


def test_migration_preserves_every_original_row_trigger_and_exact_timestamp(old_database):
    path = old_database
    before, triggers = snapshot(path)
    backup = migration.migrate(path)
    assert backup and backup.is_file() and backup.stat().st_mode & 0o077 == 0
    assert snapshot(backup) == (before, triggers)
    with sqlite3.connect(path) as db:
        for table, expected in before.items():
            if table == "persons":
                columns = [row[1] for row in db.execute("PRAGMA table_info(persons)") if row[1] != "sex"]
                selected = ','.join('"'+name+'"' for name in columns)
                assert db.execute(f'SELECT {selected} FROM persons ORDER BY rowid').fetchall() == expected
                assert all(row == (None,) for row in db.execute("SELECT sex FROM persons"))
            else:
                assert db.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall() == expected
        assert db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall() == triggers
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE persons SET sex='guessed'")
    engine = create_engine(f"sqlite:///{path}")
    try:
        require_current_schema(engine)
    finally:
        engine.dispose()
    assert migration.migrate(path) is None
    assert len(list(path.parent.glob("*.before-name-cases-*.sqlite3"))) == 1


def test_failed_ddl_rolls_back_the_whole_migration_and_keeps_backup(old_database, monkeypatch):
    before = snapshot(old_database)
    def refuse(*args):
        raise RuntimeError("synthetic DDL refusal")
    monkeypatch.setattr(migration, "create_table", refuse)
    with pytest.raises(RuntimeError):
        migration.migrate(old_database)
    assert snapshot(old_database) == before
    with sqlite3.connect(old_database) as db:
        assert "sex" not in migration.columns(db, "persons")
    backups = list(old_database.parent.glob("*.before-name-cases-*.sqlite3"))
    assert len(backups) == 1 and snapshot(backups[0]) == before


def test_migration_refuses_missing_and_unrelated_databases(tmp_path):
    missing = tmp_path / "missing.sqlite3"
    with pytest.raises(ValueError):
        migration.migrate(missing)
    assert not missing.exists()
    wrong = tmp_path / "wrong.sqlite3"
    with sqlite3.connect(wrong) as db:
        db.execute("CREATE TABLE keep_me(id INTEGER)"); db.execute("INSERT INTO keep_me VALUES(17)")
    before = wrong.read_bytes()
    with pytest.raises(ValueError, match="окрема міграція"):
        migration.migrate(wrong)
    assert wrong.read_bytes() == before
    assert not list(tmp_path.glob("*.before-name-cases-*.sqlite3"))


def test_migration_refuses_to_silently_accept_missing_history_guards(old_database):
    with sqlite3.connect(old_database) as db:
        db.execute("DROP TRIGGER guard_person_assignments_insert")
    before = snapshot(old_database)
    with pytest.raises(ValueError, match="тригери"):
        migration.migrate(old_database)
    assert snapshot(old_database) == before
    assert not list(old_database.parent.glob("*.before-name-cases-*.sqlite3"))

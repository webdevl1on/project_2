"""CLI checks use only newly allocated SQLite and Excel files in tmp_path."""

import hashlib
from pathlib import Path
import sqlite3
import subprocess
import sys

from openpyxl import Workbook

from app.database.schema_check import require_current_schema
from sqlalchemy import create_engine


ROOT = Path(__file__).resolve().parents[1]


def cli(module, path=None, *extra):
    args = [sys.executable, "-m", module]
    if path is not None:
        args.extend(["--database", str(path)])
    return subprocess.run([*args, *extra], cwd=ROOT, text=True, capture_output=True)


def digest(path):
    return hashlib.sha256(path.read_bytes()).digest()


def test_init_refuses_existing_and_requires_explicit_recreation(tmp_path):
    path = tmp_path / "new.sqlite3"
    assert cli("app.database.init_db", path).returncode == 0
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE sentinel (value TEXT)")
        db.execute("INSERT INTO sentinel VALUES ('keep')")
    before = digest(path)
    rejected = cli("app.database.init_db", path)
    assert rejected.returncode == 2 and "без --recreate" in rejected.stderr
    assert digest(path) == before
    implicit = cli("app.database.init_db", None, "--recreate")
    assert implicit.returncode == 2 and "явного --database" in implicit.stderr
    assert cli("app.database.init_db", path, "--recreate").returncode == 0
    engine = create_engine(f"sqlite:///{path}")
    try:
        require_current_schema(engine)
    finally:
        engine.dispose()
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='sentinel'").fetchone() is None


def test_recreation_refuses_non_sqlite_file_and_live_sidecars(tmp_path):
    other = tmp_path / "not_sqlite.txt"
    other.write_text("Keep this synthetic file")
    before = digest(other)
    assert cli("app.database.init_db", other, "--recreate").returncode == 2
    assert digest(other) == before
    path = tmp_path / "new.sqlite3"
    assert cli("app.database.init_db", path).returncode == 0
    sidecar = Path(str(path) + "-wal")
    sidecar.write_bytes(b"synthetic marker")
    before = digest(path)
    assert cli("app.database.init_db", path, "--recreate").returncode == 2
    assert digest(path) == before and sidecar.read_bytes() == b"synthetic marker"


def test_seed_commands_reject_old_schema_without_modifying_it(tmp_path):
    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE persons(person_id INTEGER PRIMARY KEY, tax_number TEXT)")
        db.execute("INSERT INTO persons(tax_number) VALUES ('0123456789')")
    before = digest(path)
    for module in ("app.seeds.seed_structure", "app.services.seed_test_people"):
        result = cli(module, path)
        assert result.returncode == 2
        assert "Схема SQLite застаріла" in result.stderr
        assert digest(path) == before


def sample_excel(tmp_path, *, bad_position=False):
    workbook = Workbook()
    positions = workbook.active
    positions.title = "positions"
    endings = ("nominative", "genitive", "dative", "accusative", "instrumental", "locative", "vocative")
    positions.append(["position_number", "code", "unit_short", "name_short", *[f"name_{ending}" for ending in endings]])
    positions.append(["notes"])
    positions.append(["bad" if bad_position else 10, "TEST", "Тестовий", "Посада", *["Тестова посада"] * 7])
    people = workbook.create_sheet("persons")
    people.append(["surname", "name", "patronymic", "tax_number", "birth_day", "birth_month", "birth_year", "rank", "sex"])
    people.append(["Прізвище", "Ім’я", "По батькові", "РНОКПП", "День народження", "Місяць народження", "Рік народження", "Звання", "Стать"])
    people.append(["Тестенко", "Тестослав", None, "0012345678", 29, 2, 2000, "солдат", "male"])
    people.append(["Тестов", "Тестимир", None, "0123456789", None, 3, 1995, "SENIOR_SOLDIER", "male"])
    path = tmp_path / "reference.xlsx"
    workbook.save(path)
    workbook.close()
    return path


def table_counts(path):
    names = ("event_types", "event_subtypes", "ranks", "positions", "persons", "person_names", "person_ranks")
    with sqlite3.connect(path) as db:
        return {name: db.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0] for name in names}


def test_full_cli_setup_and_repeat_reference_and_person_seeding(tmp_path):
    path = tmp_path / "fresh.sqlite3"
    excel = sample_excel(tmp_path)
    assert cli("app.database.init_db", path).returncode == 0
    first_counts = None
    for attempt in (1, 2):
        references = cli("app.seeds.seed_structure", path, "--excel", str(excel), "--version-name", "Synthetic", "--valid-from", "2000-01-01")
        assert references.returncode == 0, references.stderr
        if attempt == 1:
            assert table_counts(path)["persons"] == 0  # Test people remain a separate command.
        people = cli("app.services.seed_test_people", path, "--excel", str(excel))
        assert people.returncode == 0, people.stderr
        assert f"створено: {2 if attempt == 1 else 0}" in people.stdout
        counts = table_counts(path)
        assert counts == {"event_types": 7, "event_subtypes": 15, "ranks": 21, "positions": 1,
                          "persons": 2, "person_names": 2, "person_ranks": 2}
        if first_counts is None:
            first_counts = counts
        else:
            assert counts == first_counts
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT tax_number FROM persons ORDER BY person_id").fetchall() == [("0012345678",), ("0123456789",)]
        assert db.execute("SELECT birth_day,birth_month,birth_year FROM persons ORDER BY person_id").fetchall() == [(29, 2, 2000), (None, 3, 1995)]
        assert db.execute("SELECT rank_order_day,rank_order_month,rank_order_year,rank_order_date FROM person_ranks").fetchall() == [(None, None, None, None)] * 2


def test_reference_seed_failure_rolls_back_the_whole_reference_transaction(tmp_path):
    path = tmp_path / "fresh.sqlite3"
    excel = sample_excel(tmp_path, bad_position=True)
    assert cli("app.database.init_db", path).returncode == 0
    assert cli("app.seeds.seed_structure", path, "--excel", str(excel), "--version-name", "Synthetic", "--valid-from", "2000-01-01").returncode == 2
    assert all(count == 0 for count in table_counts(path).values())


def test_reference_seed_does_not_create_missing_database(tmp_path):
    path = tmp_path / "absent.sqlite3"
    assert cli("app.seeds.seed_structure", path).returncode == 2
    assert not path.exists()

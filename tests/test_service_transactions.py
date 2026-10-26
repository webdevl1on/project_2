"""Real SQLite regression coverage for service ownership and composition."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func, event
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.models import Person, PersonName, PersonRank, Rank, EventType, EventSubtype, PersonEvent
from app.models.reference_data.ranks import ReferenceRanks
from app.repositories.person_repository import PersonRepository
from app.services.service_person_create import ServicePersonCreate as People
from app.services.service_person_name import ServicePersonNameFunc as Names
from app.services.service_person_rank import ServicePersonRankFunc as Ranks
from app.services.service_for_person_event import PersonEventService as Events


@pytest.fixture
def factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'services.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    with factory.begin() as db:
        db.add_all(Rank(**row) for row in ReferenceRanks.RANKS)
        kind = EventType(event_type="test", event_name="Синтетична подія")
        other = EventType(event_type="other", event_name="Інша синтетична подія")
        db.add_all([kind, other])
        db.flush()
        db.add(EventSubtype(event_type_id=other.event_type_id, event_subtype="other", event_subtype_name="Інший підтип"))
    yield factory
    engine.dispose()


def data(**changes):
    return {"sex": "male", "surname": "Тестовий", "name": "Тарас", "tax_number": "0123456789",
            "birth_month": 3, "birth_year": 1993, **changes}


def test_person_and_initial_name_rollback_together(factory, monkeypatch):
    def refuse(*args, **kwargs):
        raise RuntimeError("injected name failure")
    with factory() as db:
        with monkeypatch.context() as patch:
            patch.setattr(PersonRepository, "add_name", refuse)
            with pytest.raises(RuntimeError):
                People.create_person(data(), db)
        assert db.scalar(select(func.count()).select_from(Person)) == 0
        assert db.scalar(select(func.count()).select_from(PersonName)) == 0
        assert People.create_person(data(), db).tax_number == "0123456789"


def test_name_activation_is_rolled_back_on_flush_failure(factory):
    with factory() as db:
        person = People.create_person(data(), db)
        person_id = person.person_id
        def refuse(*args):
            raise RuntimeError("injected flush failure")
        event.listen(db, "before_flush", refuse)
        try:
            with pytest.raises(RuntimeError):
                Names.add_new_name(person_id, {"surname": "Інший", "name": "Тарас"}, db)
        finally:
            event.remove(db, "before_flush", refuse)
        names = PersonRepository.name_history(db, person_id)
        assert [(name.surname, name.is_active) for name in names] == [("Тестовий", True)]


def test_people_and_rank_can_share_outer_transaction(factory):
    with pytest.raises(RuntimeError):
        with factory.begin() as db:
            person = People.create_person(data(), db, commit=False)
            rank = db.scalar(select(Rank))
            Ranks.add_rank(person.person_id, {"rank_id": rank.rank_id, "rank_order_year": 2020}, db, commit=False)
            raise RuntimeError("outer operation failed")
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Person)) == 0
        assert db.scalar(select(func.count()).select_from(PersonRank)) == 0


def test_people_names_ranks_and_event_commit_once_as_one_operation(factory):
    commits = []
    with factory.begin() as db:
        event.listen(db, "after_commit", lambda session: commits.append(True))
        person = People.create_person(data(), db, commit=False)
        renamed = Names.add_new_name(person.person_id, {"surname": "Інший", "name": "Тарас"}, db, commit=False)
        Names.update_person_name(renamed.person_name_id, {"name": "Петро"}, db, commit=False)
        rank = db.scalar(select(Rank))
        Ranks.add_rank(person.person_id, {"rank_id": rank.rank_id}, db, commit=False)
        kind = db.scalar(select(EventType))
        created = Events.create_person_event(person.person_id, kind.event_type_id, date_start="01.02.2025", db=db)
        assert created.event_id and not commits
    assert len(commits) == 1
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Person)) == 1
        assert db.scalar(select(func.count()).select_from(PersonName)) == 2
        assert db.scalar(select(func.count()).select_from(PersonRank)) == 1
        assert db.scalar(select(func.count()).select_from(PersonEvent)) == 1
        assert db.scalar(select(PersonName).where(PersonName.is_active.is_(True))).name == "Петро"


def test_standalone_operation_refuses_pending_caller_writes(factory):
    with factory() as db:
        pending = Person(tax_number="1234567890")
        db.add(pending)
        with pytest.raises(ValueError, match="незбережені"):
            People.create_person(data(), db)
        assert pending in db.new
        db.rollback()


def test_rank_history_edit_activation_delete_and_validation(factory):
    with factory() as db:
        person = People.create_person(data(), db)
        choices = PersonRepository.ranks(db)
        first = Ranks.add_rank(person.person_id, {"rank_id": choices[0].rank_id}, db)
        second = Ranks.add_rank(person.person_id, {"rank_id": choices[1].rank_id, "rank_order_year": 2024}, db)
        assert first.is_active and not second.is_active
        with pytest.raises(ValueError, match="вже є"):
            Ranks.add_rank(person.person_id, {"rank_id": choices[1].rank_id}, db)
        updated = Ranks.update_person_rank(second.person_rank_id, {"rank_id": choices[1].rank_id, "rank_order_month": 2, "rank_order_year": 2024}, db)
        assert updated.rank_order_day is None and updated.rank_order_month == 2
        Ranks.change_person_rank_to_active(second.person_rank_id, db)
        assert not first.is_active and second.is_active
        with pytest.raises(ValueError):
            Ranks.delete_person_rank(second.person_rank_id, "DELETE", db)
        Ranks.delete_person_rank(first.person_rank_id, "DELETE", db)
        assert db.get(PersonRank, first.person_rank_id) is None


def test_name_history_activation_and_confirmed_deletion(factory):
    with factory() as db:
        person = People.create_person(data(), db)
        first = PersonRepository.current_name(db, person.person_id)
        second = Names.add_new_name(person.person_id, {"surname": "Інший", "name": "Тарас"}, db)
        Names.change_person_name_to_active(first.person_name_id, db)
        assert first.is_active and not second.is_active
        with pytest.raises(ValueError, match="DELETE"):
            Names.delete_person_name(second.person_name_id, "no", db)
        assert db.get(PersonName, second.person_name_id) is not None
        with pytest.raises(ValueError, match="active"):
            Names.delete_person_name(first.person_name_id, "DELETE", db)
        second_id = second.person_name_id
        Names.delete_person_name(second_id, "DELETE", db)
        assert db.get(PersonName, second_id) is None and first.is_active


def test_existing_person_pages_and_failed_edit_contract(factory):
    from app.main import app
    from app.database.db import get_db
    def override():
        with factory() as db:
            yield db
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = override
    try:
        with TestClient(app) as client:
            with factory() as db:
                rank_id = db.scalar(select(Rank.rank_id))
            response = client.post("/persons/new", data=data(rank_id=rank_id), follow_redirects=False)
            assert response.status_code == 303
            with factory() as db:
                key = db.scalar(select(Person.person_id))
            assert response.headers["location"] == f"/persons/{key}/created"
            assert client.get(response.headers["location"]).status_code == 200
            for url in ["/persons", f"/person_detail/{key}", f"/person_full_info/{key}", f"/persons/{key}/edit"]:
                assert client.get(url).status_code == 200
            bad = client.post(f"/persons/{key}/edit", data=data(birth_day=31, birth_month=2))
            assert bad.status_code == 400
            with factory() as db:
                assert db.get(Person, key).birth_day is None
            assert client.post(f"/persons/{key}/edit", data=data(name="Петро")).status_code == 200
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def create_event(factory, **changes):
    with factory() as db:
        person = People.create_person(data(), db)
        person_id = person.person_id
        kind_id = db.scalar(select(EventType.event_type_id).order_by(EventType.event_type_id))
    event = Events.create_person_event(person_id, kind_id, date_start="01.02.2025", date_end="10.02.2025",
                                     session_factory=factory, **changes)
    return event, person_id, kind_id


def test_external_event_session_joins_people_transaction_and_never_commits_or_closes(factory):
    with pytest.raises(RuntimeError):
        with factory.begin() as db:
            commits = []
            event.listen(db, "after_commit", lambda session: commits.append(True))
            person = People.create_person(data(), db, commit=False)
            kind_id = db.scalar(select(EventType.event_type_id))
            created = Events.create_person_event(person.person_id, kind_id, date_start="01.02.2025", db=db)
            assert created.event_id and not commits
            assert Events.get_person_event_by_date(person.person_id, "02.02.2025", db=db) == [created]
            assert db.is_active and db.in_transaction()
            raise RuntimeError("roll back the entire business operation")
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(PersonEvent)) == 0
        assert db.scalar(select(func.count()).select_from(Person)) == 0


def test_event_standalone_create_edit_query_conflict_delete_contract(factory):
    created, person_id, kind_id = create_event(factory, note=" Початкова примітка ")
    assert created.note == "Початкова примітка"  # Loaded after standalone close.
    conflicts = Events.create_person_event(person_id, kind_id, date_start="05.02.2025", session_factory=factory)
    assert [item.event_id for item in conflicts] == [created.event_id]
    assert conflicts[0].date_start.day == 1
    changed = Events.change_person_event(created.event_id, kind_id, date_start="02.02.2025", duration="3",
                                        note="Виправлено", session_factory=factory)
    assert changed.event_id == created.event_id and changed.date_end.day == 4
    assert [row.event_id for row in Events.get_person_event_by_date(person_id, "03.02.2025", session_factory=factory)] == [created.event_id]
    assert Events.delete_person_event(created.event_id, session_factory=factory)
    assert not Events.delete_person_event(created.event_id, session_factory=factory)


@pytest.mark.parametrize("field, value", [("date_start", "_.02.2025"), ("date_end", "_._.2025"),
                                         ("order_date", "01._.2025"), ("date_start", None),
                                         ("date_end", "31.02.2025"), ("date_end", "31.01.2025")])
def test_failed_event_edit_preserves_stored_event(factory, field, value):
    created, person_id, kind_id = create_event(factory, note="Незмінна примітка")
    values = {"date_start": "01.02.2025", "date_end": "10.02.2025", field: value}
    with pytest.raises(ValueError):
        Events.change_person_event(created.event_id, kind_id, session_factory=factory, **values)
    with factory() as db:
        saved = db.get(PersonEvent, created.event_id)
        assert saved.note == "Незмінна примітка" and saved.date_start.day == 1 and saved.date_end.day == 10


def test_external_event_change_and_delete_are_reversible(factory):
    created, _, kind_id = create_event(factory)
    with factory() as db:
        changed = Events.change_person_event(created.event_id, kind_id, date_start="02.02.2025", db=db)
        assert changed.date_start.day == 2
        db.rollback()
        assert db.get(PersonEvent, created.event_id).date_start.day == 1
        assert Events.delete_person_event(created.event_id, db=db)
        db.rollback()
        assert db.get(PersonEvent, created.event_id) is not None


def test_event_write_failure_rolls_back_and_closes_owned_session(factory):
    created, _, kind_id = create_event(factory, note="Стара примітка")
    sessions = []
    def failing_factory():
        db = factory()
        sessions.append(db)
        def fail(*args):
            raise RuntimeError("synthetic database refusal")
        event.listen(db, "before_flush", fail)
        return db
    with pytest.raises(RuntimeError):
        Events.change_person_event(created.event_id, kind_id, date_start="01.02.2025", note="Не збережено",
                                   session_factory=failing_factory)
    assert not sessions[0].in_transaction()
    with factory() as db:
        assert db.get(PersonEvent, created.event_id).note == "Стара примітка"


def test_wrong_event_subtype_does_not_persist_changes(factory):
    created, _, kind_id = create_event(factory)
    with factory() as db:
        subtype_id = db.scalar(select(EventSubtype.event_subtype_id))
    with pytest.raises(ValueError, match="does not belong"):
        Events.change_person_event(created.event_id, kind_id, event_subtype_id=subtype_id,
                                   date_start="01.02.2025", session_factory=factory)
    with factory() as db:
        assert db.get(PersonEvent, created.event_id).event_subtype_id is None


def test_session_and_factory_cannot_be_combined(factory):
    with factory() as db:
        with pytest.raises(ValueError, match="не обидві"):
            Events.delete_person_event(1, db=db, session_factory=factory)


def test_diagnostic_imports_have_no_database_io(monkeypatch):
    import importlib
    import app.database.transactions as transactions
    def refuse():
        raise AssertionError("Import must not open a database")
    monkeypatch.setattr(transactions, "SessionLocal", refuse)
    for module in ("app.services.check_events", "app.services.check_person_events"):
        importlib.reload(importlib.import_module(module))

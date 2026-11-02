"""Inclusive event workflow on isolated synthetic SQLite, never a working DB."""
from datetime import date, timedelta
import pytest
from sqlalchemy import select, func, event
from fastapi.testclient import TestClient
from app.database.db import get_db
from app.models import PersonEvent, EventType, EventSubtype, Person
from app.services import person_events as editor
from app.services.service_for_person_event import PersonEventService as Events
from app.services.service_person_create import ServicePersonCreate as People
from tests.test_service_transactions import factory, data


@pytest.fixture
def person(factory):
    with factory() as db:
        kind=db.scalar(select(EventType).order_by(EventType.event_type_id));kind.event_type="SERVICE";db.commit()
        record = People.create_person(data(), db)
        return record.person_id, db.scalar(select(EventType.event_type_id).order_by(EventType.event_type_id))


def create(factory, person, start='2026-10-01', end=None, **extra):
    pid, kind = person
    return Events.create_person_event(pid, kind, date_start=date.fromisoformat(start), date_end=date.fromisoformat(end) if end else None, session_factory=factory, **extra)


def snapshot(db, pid):
    return [(r.event_id, r.date_start, r.date_end, r.duration) for r in db.scalars(select(PersonEvent).where(PersonEvent.person_id == pid).order_by(PersonEvent.event_id))]


def test_closed_open_and_inclusive_duration(factory, person):
    closed = create(factory, person, end='2026-10-10')
    opened = create(factory, person, start='2026-10-11')
    assert closed.duration == 10
    assert opened.date_end is opened.duration is None
    with factory() as db:
        rows = editor.page(db, person[0])['events']
        assert rows[0]['period'] == '11.10.2026 — по сьогодні'
        assert rows[0]['date_end'] is None
        assert len(Events.get_person_event_by_date(person[0], '10.10.2026', '10.10.2026', db=db)) == 1
        assert [r.event_id for r in Events.get_person_event_by_date(person[0], '10.10.2026', '11.10.2026', db=db)] == [closed.event_id, opened.event_id]


@pytest.mark.parametrize('closed_new', [False, True])
def test_create_closes_only_previous_open_event(factory, person, closed_new):
    previous = create(factory, person)
    current = create(factory, person, start='2026-10-15', end='2026-10-20' if closed_new else None)
    with factory() as db:
        old = db.get(PersonEvent, previous.event_id)
        assert old.date_end == date(2026,10,14) and old.duration == 14
        assert current.event_id != previous.event_id
        assert current.duration == (6 if closed_new else None)


def test_creation_today_uses_the_day_before_without_a_clock_default(factory, person):
    from app.services.staff_service import today
    on = today()
    old = create(factory, person, start=(on-timedelta(days=5)).isoformat())
    current = create(factory, person, start=on.isoformat())
    with factory() as db:
        assert db.get(PersonEvent, old.event_id).date_end == on-timedelta(days=1)
        assert db.get(PersonEvent, old.event_id).duration == 5
        assert current.date_end is None


@pytest.mark.parametrize('start,end', [('2026-10-10','2026-10-20'),('2026-10-05','2026-10-08'),('2026-09-30','2026-10-01')])
def test_completed_overlap_and_shared_boundary_are_refused(factory, person, start, end):
    previous = create(factory, person, end='2026-10-10')
    result = create(factory, person, start=start, end=end)
    assert isinstance(result, list) and [r.event_id for r in result] == [previous.event_id]
    with factory() as db:
        assert snapshot(db, person[0]) == [(previous.event_id, date(2026,10,1), date(2026,10,10), 10)]


@pytest.mark.parametrize('start', ['2026-09-30', '2026-10-01'])
def test_cannot_close_an_open_event_before_its_start(factory, person, start):
    previous = create(factory, person)
    assert isinstance(create(factory, person, start=start), list)
    with factory() as db:
        assert db.get(PersonEvent, previous.event_id).date_end is None
        assert db.scalar(select(func.count()).select_from(PersonEvent)) == 1


@pytest.mark.parametrize('additional_start,additional_end', [('2026-10-20',None),('2026-10-05','2026-10-10'),('2026-10-15','2026-10-25')])
def test_all_conflicts_leave_previous_event_and_new_record_unchanged(factory, person, additional_start, additional_end):
    previous = create(factory, person)
    with factory.begin() as db:
        db.add(PersonEvent(person_id=person[0], event_type_id=person[1], date_start=date.fromisoformat(additional_start), date_end=date.fromisoformat(additional_end) if additional_end else None))
    with factory() as db:
        before = snapshot(db, person[0])
        with pytest.raises(editor.EventConflictError) as error:
            editor.save(db, person[0], {'event_type_id':person[1], 'date_start':'2026-10-15'})
        assert len(error.value.conflicts) == 2
        assert snapshot(db, person[0]) == before
        assert db.get(PersonEvent, previous.event_id).date_end is None


def test_insert_refusal_rolls_back_automatic_closure(factory, person):
    old = create(factory, person)
    def refuse(*args):
        raise RuntimeError('synthetic insert refusal')
    event.listen(PersonEvent, 'before_insert', refuse)
    try:
        with factory() as db:
            with pytest.raises(RuntimeError):
                editor.save(db, person[0], {'event_type_id':person[1], 'date_start':'2026-10-15'})
            assert snapshot(db, person[0]) == [(old.event_id, date(2026,10,1), None, None)]
    finally:
        event.remove(PersonEvent, 'before_insert', refuse)


def test_edit_keeps_id_and_checks_conflicts_without_closing_other_events(factory, person):
    first = create(factory, person, end='2026-10-10')
    second = create(factory, person, start='2026-10-11')
    with factory() as db:
        values = next(r for r in editor.page(db, person[0])['events'] if r['event_id']==first.event_id)
        editor.save(db, person[0], {**values, 'date_end':'2026-10-09','duration':''}, first.event_id)
        assert db.get(PersonEvent, first.event_id).duration == 9
        current = next(r for r in editor.page(db, person[0])['events'] if r['event_id']==first.event_id)
        with pytest.raises(editor.EventConflictError):
            editor.save(db, person[0], {**current, 'date_end':'2026-10-11','duration':''}, first.event_id)
        assert db.get(PersonEvent, first.event_id).date_end == date(2026,10,9)
        assert db.get(PersonEvent, second.event_id).date_end is None
        with pytest.raises(editor.EventConflictError, match='вже змінено'):
            editor.save(db, person[0], values, first.event_id)


@pytest.mark.parametrize('changes,field', [({'date_start':'_.10.2026'},'date_start'),({'date_end':'2026-09-30'},'date_end'),({'date_end':'2026-10-10','duration':'2'},'duration'),({'duration':'0'},'duration'),({'duration':'999999999999999'},'duration'),({'order_date':'_.10.2026'},'order_date'),({'event_subtype_id':1},'event_subtype_id')])
def test_invalid_fields_never_leave_a_record(factory, person, changes, field):
    with factory() as db:
        with pytest.raises(ValueError) as error:
            editor.save(db, person[0], {'event_type_id':person[1],'date_start':'2026-10-01',**changes})
        assert getattr(error.value, 'field', None) == field
        assert db.scalar(select(func.count()).select_from(PersonEvent)) == 0


def test_inactive_catalog_entries_are_retained_only_for_their_own_history(factory, person):
    record = create(factory, person)
    with factory() as db:
        db.get(EventType, person[1]).event_is_active = False
        db.commit()
        state = editor.page(db, person[0])
        assert state['events'][0]['type_name'] == 'Синтетична подія'
        assert not next(t for t in state['types'] if t['id']==person[1])['active']
        with pytest.raises(ValueError, match='неактивний'):
            editor.save(db, person[0], {'event_type_id':person[1],'date_start':'2026-11-01'})
        editor.save(db, person[0], {**state['events'][0], 'note':'Уточнення'}, record.event_id)
        assert db.get(PersonEvent, record.event_id).note == 'Уточнення'


def test_http_errors_preserve_database_and_return_all_conflicts(factory, person):
    from app.main import app
    first = create(factory, person, end='2026-10-10')
    def session():
        with factory() as db: yield db
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = session
    try:
        with TestClient(app) as client:
            base = f'/persons/{person[0]}/events'
            response = client.post(base, data={'event_type_id':person[1], 'date_start':'2026-10-05'})
            assert response.status_code == 409
            assert response.json()['conflicts'][0]['event_id'] == first.event_id
            response = client.post(base, data={'event_type_id':person[1], 'date_start':'2026-10-01','date_end':'2026-09-30'})
            assert response.status_code == 422 and response.json()['field'] == 'date_end'
            assert client.post(base, headers={'Origin':'https://foreign.invalid'}, data={}).status_code == 403
            assert client.get(base).headers['cache-control'] == 'no-store'
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)

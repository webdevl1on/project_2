"""Event periods and real HTTP concurrency, only in isolated project2_ci schemas."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import date
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, func, event
from app.models import Person, PersonEvent, EventType, EventSubtype, Position, StaffVersion, PersonAssignment, PersonServiceHistory
from app.database.db import get_db
from app.services import person_events as editor
from app.services.staff_service import StaffService


@pytest.fixture
def events(pg_factory):
    with pg_factory.begin() as db:
        person=Person(sex='male');kind=EventType(event_type='SERVICE',event_name='Служба')
        vacation=EventType(event_type='VACATION',event_name='Відпустка')
        db.add_all([person,kind,vacation]);db.flush()
        sub=EventSubtype(event_type_id=vacation.event_type_id,event_subtype='ANNUAL',event_subtype_name='Основна')
        db.add(sub);db.flush()
        return pg_factory,person.person_id,kind.event_type_id,vacation.event_type_id,sub.event_subtype_id


def test_event_crud_open_closure_and_edit_on_postgresql(events):
    factory,pid,service,vacation,sub=events
    with factory() as db:
        old=editor.save(db,pid,{'event_type_id':service,'date_start':'2026-10-01'})
        current=editor.save(db,pid,{'event_type_id':service,'date_start':'2026-10-15'})
        assert (db.get(PersonEvent,old).date_end,db.get(PersonEvent,old).duration)==(date(2026,10,14),14)
        state=editor.page(db,pid)['events']
        assert state[0]['event_id']==current and state[0]['period'].endswith('по сьогодні')
        with pytest.raises(editor.EventConflictError):
            editor.save(db,pid,{'event_type_id':service,'date_start':'2026-10-14','date_end':'2026-10-16'})
        original=next(r for r in state if r['event_id']==old)
        editor.save(db,pid,{**original,'date_end':'2026-10-13','duration':'','note':'Уточнення'},old)
        assert db.get(PersonEvent,old).duration==13
        assert db.get(PersonEvent,old).note=='Уточнення'
        assert db.scalar(select(func.count()).select_from(PersonEvent))==2


def test_concurrent_http_creates_close_previous_exactly_once(events):
    from app.main import app
    factory,pid,service,vacation,sub=events
    with factory() as db:old=editor.save(db,pid,{'event_type_id':service,'date_start':'2026-10-01'})
    def session():
        with factory() as db:yield db
    overrides=app.dependency_overrides.copy();app.dependency_overrides[get_db]=session
    try:
        with TestClient(app) as client:
            barrier=Barrier(2)
            def request(index):
                barrier.wait(timeout=5)
                return client.post(f'/persons/{pid}/events',data={'event_type_id':service,'date_start':'2026-10-15','note':str(index)}).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(request,[1,2]))
        assert sorted(statuses)==[200,409]
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(PersonEvent))==2
            assert db.get(PersonEvent,old).date_end==date(2026,10,14)
            assert db.get(PersonEvent,old).duration==14
    finally:
        app.dependency_overrides.clear();app.dependency_overrides.update(overrides)


def test_postgresql_insert_failure_rolls_back_closure(events):
    factory,pid,service,vacation,sub=events
    with factory() as db:old=editor.save(db,pid,{'event_type_id':service,'date_start':'2026-10-01'})
    def refuse(*args):raise RuntimeError('synthetic insert refusal')
    event.listen(PersonEvent,'before_insert',refuse)
    try:
        with factory() as db:
            with pytest.raises(RuntimeError):editor.save(db,pid,{'event_type_id':service,'date_start':'2026-10-15'})
            assert db.get(PersonEvent,old).date_end is None
            assert db.scalar(select(func.count()).select_from(PersonEvent))==1
    finally:event.remove(PersonEvent,'before_insert',refuse)


def test_events_survive_position_change_and_exist_without_assignments(events):
    from tests.test_person_positions import make_position
    from app.services.assignment_events import event_positions
    factory,pid,service,vacation,sub=events
    with factory() as db:
        key=editor.save(db,pid,{'event_type_id':service,'date_start':'2026-10-01'})
        assert editor.page(db,pid)['events'][0]['event_id']==key
        assert db.scalar(select(func.count()).select_from(PersonAssignment))==0
        structure=StaffService.create_structure(db,'events','Тест')
        version=StaffVersion(staff_structure_id=structure,name='Тест',valid_from=date(2026,1,1));db.add(version);db.flush()
        positions=[make_position(n,'Тест','Посада','Посада') for n in (10,20)]
        for position in positions:position.staff_version_id=version.id
        db.add_all(positions);db.commit()
        first=StaffService.create_assignment(db,pid,positions[0].position_id,date(2026,1,1))
        row=db.get(PersonAssignment,first)
        StaffService.correct_assignment(db,first,row.revision,pid,positions[0].position_id,date(2026,1,1),date(2026,10,14))
        StaffService.create_assignment(db,pid,positions[1].position_id,date(2026,10,15))
        original=db.get(PersonEvent,key)
        assert original.date_start==date(2026,10,1) and original.date_end is None
        assert len(event_positions(db,original,date(2026,10,31))['positions'])==2
        assert db.scalar(select(func.count()).select_from(PersonServiceHistory))==0


def test_journal_and_date_presence_read_postgresql_without_changing_history(events):
    from app.services import event_views
    factory,pid,service,vacation,sub=events
    with factory() as db:
        key=editor.save(db,pid,{'event_type_id':vacation,'date_start':'2026-10-01','date_end':'2026-10-03'})
        later=editor.save(db,pid,{'event_type_id':service,'date_start':'2026-10-04'})
        payload=event_views.journal(db,{'start':'2026-10-01','end':'2026-10-07','scale':'week'})
        assert payload['people']==[] and len(payload['buckets'])==2 # No official assignment at the snapshot date.
        assert db.get(PersonEvent,key).date_start==date(2026,10,1)
        assert event_views.presence_for_people(db,[pid],date(2026,10,3))[pid]['label']=='відпустка'
        assert event_views.presence_for_people(db,[pid],date(2026,10,4))[pid]['label']=='служба'
        assert db.get(PersonEvent,key).date_end==date(2026,10,3)
        assert db.get(PersonEvent,later).date_end is None
        assert db.scalar(select(func.count()).select_from(PersonAssignment))==0

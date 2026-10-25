"""All data/engines are isolated. No compatibility fixture or implicit dates here."""
from datetime import date as D, datetime, UTC
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.exc import IntegrityError
from fastapi.testclient import TestClient
from app.database.base import Base
from app.database.db import get_db
from app.models import StaffStructure, StaffVersion, PersonAssignment, Position, Person, PersonName, PersonRank, PersonEvent, EventType
from app.main import app
from app.services.staff_service import StaffService as Service, assignments_at, write_unit
from app.services.staff_import import preview_import, import_version, read_positions
from app.services.assignment_events import event_positions, events_for_people, events_for_staff
from app.services.person_picker import person_options
from app.services.staff_tokens import sign
from tests.test_person_positions import make_position, make_rank


@pytest.fixture
def store():
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:yield db
    engine.dispose()


def setup(db):
    structure=StaffStructure(code='test',name='Тестовий штат')
    v1=StaffVersion(structure=structure,name='Архів',valid_from=D(2026,1,1),valid_to=D(2026,5,31))
    v2=StaffVersion(structure=structure,name='Поточний',valid_from=D(2026,6,1))
    positions=[make_position(15,'А','Стрілець','Історичний стрілець'),make_position(15,'Б','Сапер','Сапер'),make_position(27,'Б','Водій','Водій')]
    positions[0].staff_version=v1
    for p in positions[1:]:p.staff_version=v2
    people=[Person(birth_month=4,birth_year=1998),Person(birth_month=4,birth_year=1998),Person()]
    rank=make_rank()
    db.add_all([structure,*positions,*people,rank]);db.flush()
    for person in people:
        db.add(PersonName(person_id=person.person_id,surname='Тестенко',name='Іван',patronymic='Петрович'))
        db.add(PersonRank(person_id=person.person_id,rank_id=rank.rank_id))
    db.commit()
    return structure,[v1,v2],positions,people


def workbook(*,sheet='positions',bad_header=False,duplicate=False,bad_row=False):
    book=Workbook();ws=book.active;ws.title=sheet
    cols=['position_number','code','unit_short','name_short',*[f'name_{case}' for case in ('nominative','genitive','dative','accusative','instrumental','locative','vocative')]]
    ws.append(cols[:-1] if bad_header else cols);ws.append(['notes'])
    ws.append(['bad' if bad_row else 15,'TEST','Тестовий','Посада',*['Тестова посада']*7])
    if duplicate:ws.append([15,'OTHER','Інший','Посада',*['Посада']*7])
    other=book.create_sheet('persons');other.append(['this sheet must not be imported'])
    stream=BytesIO();book.save(stream);book.close();stream.seek(0);return stream


def test_one_source_and_exact_periods(store):
    assert 'person_positions' not in inspect(store.bind).get_table_names()
    _,versions,positions,people=setup(store)
    assert positions[0].position_number==positions[1].position_number
    assert positions[0].position_id!=positions[1].position_id
    key=Service.create_assignment(store,people[0].person_id,positions[0].position_id,D(2026,1,15),D(2026,4,30))
    assert assignments_at(store,D(2026,2,1)).one().id==key
    assert assignments_at(store,D(2026,6,1)).count()==0
    assert store.get(PersonAssignment,key).created_at.year>=2026
    assert positions[0].name_nominative=='Історичний стрілець'
    for start,end in ((D(2025,12,31),D(2026,2,1)),(D(2026,5,20),None),(D(2026,5,20),D(2026,6,1))):
        with pytest.raises(ValueError):Service.create_assignment(store,people[1].person_id,positions[0].position_id,start,end)


def test_history_conflicts_and_corrections(store):
    _,versions,positions,people=setup(store)
    key=Service.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1),D(2026,7,31))
    for person,pos in ((people[0],positions[2]),(people[1],positions[1])):
        with pytest.raises(ValueError):Service.create_assignment(store,person.person_id,pos.position_id,D(2026,7,15),D(2026,8,1))
    revision=store.get(PersonAssignment,key).revision
    Service.correct_assignment(store,key,revision,people[0].person_id,positions[1].position_id,D(2026,6,5),D(2026,7,25))
    assert store.query(PersonAssignment).count()==1
    assert store.get(PersonAssignment,key).assigned_from==D(2026,6,5)
    with pytest.raises(ValueError):Service.correct_assignment(store,key,revision,people[0].person_id,positions[1].position_id,D(2026,6,1),None)
    Service.correct_position(store,positions[0].position_id,positions[0].revision,{'name_nominative':'Виправлений стрілець'})
    assert store.get(Position,positions[1].position_id).name_nominative=='Сапер'
    assert store.get(Position,positions[0].position_id).name_nominative=='виправлений стрілець'


def test_reassign_preserves_previous_record_and_requires_current_confirmation(store):
    _,versions,positions,people=setup(store)
    key=Service.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    day=D(2026,8,1)
    snapshot=Service.assignment_snapshot(store,positions[2].position_id,people[0].person_id,day)
    with pytest.raises(ValueError,match='підтвердження'):Service.assign(store,positions[2].position_id,people[0].person_id,day,snapshot)
    assert store.get(PersonAssignment,key).assigned_to is None
    Service.assign(store,positions[2].position_id,people[0].person_id,day,snapshot,True)
    assert store.get(PersonAssignment,key).assigned_to==D(2026,7,31)
    assert store.query(PersonAssignment).count()==2
    with pytest.raises(ValueError,match='починається обраного дня'):
        Service.assignment_snapshot(store,positions[1].position_id,people[0].person_id,day)
    same=Service.assignment_snapshot(store,positions[2].position_id,people[0].person_id,day)
    assert 'уже призначений' in Service.assign(store,positions[2].position_id,people[0].person_id,day,same)
    assert store.query(PersonAssignment).count()==2
    with pytest.raises(ValueError,match='змінилося'):Service.assign(store,positions[2].position_id,people[0].person_id,day,snapshot,True)
    assert assignments_at(store,day).one().position_id==positions[2].position_id


def test_occupied_target_and_rollback_after_old_period_was_closed(store,monkeypatch):
    _,versions,positions,people=setup(store)
    old=Service.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    occupied=Service.create_assignment(store,people[1].person_id,positions[2].position_id,D(2026,6,1),D(2026,7,31))
    with pytest.raises(ValueError,match='зайнята'):Service.assignment_snapshot(store,positions[2].position_id,people[0].person_id,D(2026,7,1))
    on=D(2026,8,1);snapshot=Service.assignment_snapshot(store,positions[2].position_id,people[0].person_id,on)
    from sqlalchemy import event
    def fail(mapper,connection,target):raise RuntimeError('Synthetic insert failure')
    event.listen(PersonAssignment,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):Service.assign(store,positions[2].position_id,people[0].person_id,on,snapshot,True)
    finally:event.remove(PersonAssignment,'before_insert',fail)
    assert store.get(PersonAssignment,old).assigned_to is None
    assert store.query(PersonAssignment).count()==2


def test_atomic_version_closure_and_cross_version_move(store):
    _,versions,positions,people=setup(store)
    # Historical transition preserves records of two versions.
    first=Service.create_assignment(store,people[0].person_id,positions[0].position_id,D(2026,1,1),D(2026,5,31))
    snapshot=Service.assignment_snapshot(store,positions[1].position_id,people[0].person_id,D(2026,6,1))
    Service.assign(store,positions[1].position_id,people[0].person_id,D(2026,6,1),snapshot)
    assert store.get(PersonAssignment,first).assigned_to==D(2026,5,31)
    version=store.get(StaffVersion,versions[1].id);revision=version.revision
    Service.close_version(store,version.id,revision,D(2026,9,30))
    assert assignments_at(store,D(2026,10,1)).count()==0
    assert store.query(PersonAssignment).count()==2
    assert all(record.assigned_to<=D(2026,9,30) for record in store.query(PersonAssignment))
    with pytest.raises(ValueError):Service.correct_version(store,version.id,version.revision,'Wrong',D(2026,7,1),D(2026,9,30))
    assert store.get(StaffVersion,version.id).valid_from==D(2026,6,1)


def test_closure_with_later_assignment_rejects_without_partial_changes(store):
    _,versions,positions,people=setup(store)
    first=Service.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    Service.create_assignment(store,people[1].person_id,positions[2].position_id,D(2026,9,1))
    with pytest.raises(ValueError):Service.close_version(store,versions[1].id,versions[1].revision,D(2026,8,31))
    assert store.get(StaffVersion,versions[1].id).valid_to is None
    assert store.get(PersonAssignment,first).assigned_to is None


@pytest.mark.parametrize('kwargs', [{'sheet':'wrong'},{'bad_header':True},{'duplicate':True},{'bad_row':True}])
def test_excel_errors_never_create_versions(store,kwargs):
    try:
        preview=preview_import(store,workbook(**kwargs),None,'Test',D(2026,1,1),D(2026,5,31),False)
    except ValueError:
        assert store.query(StaffVersion).count()==0
        return
    assert preview['errors']
    with pytest.raises(ValueError):import_version(store,preview,'bad')
    assert store.query(StaffStructure).count()==0
    assert store.query(Position).count()==0


def test_excel_import_preview_confirm_repeat_and_period_conflict(store):
    preview=preview_import(store,workbook(),None,'Архів',D(2026,1,1),D(2026,5,31),False)
    assert not preview['errors'] and preview['units']==1
    assert store.query(StaffVersion).count()==0
    key=import_version(store,preview,'request-1')
    assert store.query(Position).count()==1 and store.query(PersonAssignment).count()==0
    assert store.query(Person).count()==0
    with pytest.raises(ValueError):import_version(store,preview,'request-1')
    structure=store.get(StaffVersion,key).staff_structure_id
    conflict=preview_import(store,workbook(),structure,'Overlap',D(2026,5,1),D(2026,6,1),False)
    assert conflict['errors']
    next_preview=preview_import(store,workbook(),structure,'New',D(2026,6,1),None,True)
    second=import_version(store,next_preview,'request-2')
    assert store.query(Position).count()==2
    assert store.query(Position).filter_by(position_number=15).count()==2
    assert store.query(PersonAssignment).count()==0


def test_excel_import_rollback_after_version_creation(store):
    prepared=preview_import(store,workbook(),None,'Rollback',D(2026,1,1),D(2026,5,31),False)
    from sqlalchemy import event
    def fail(*args):raise RuntimeError('Synthetic position failure')
    event.listen(Position,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):import_version(store,prepared,'rollback-key')
    finally:event.remove(Position,'before_insert',fail)
    assert store.query(StaffStructure).count()==store.query(StaffVersion).count()==store.query(Position).count()==0


def test_event_positions_preserve_note_and_unknown_periods(store):
    _,versions,positions,people=setup(store)
    kind=EventType(event_type='test',event_name='Тест');store.add(kind);store.flush()
    event=PersonEvent(person_id=people[0].person_id,event_type_id=kind.event_type_id,date_start=D(2026,2,1),date_end=D(2026,8,31),note='Власна примітка')
    store.add(event);store.commit()
    assert event_positions(store,event)['position_status']=='Інформація про посаду відсутня'
    assert events_for_people(store,[people[0].person_id],D(2026,1,1),D(2026,9,1))==[event]
    Service.create_assignment(store,people[0].person_id,positions[0].position_id,D(2026,1,1),D(2026,4,30))
    Service.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    result=event_positions(store,event)
    assert [item['name'] for item in result['positions']]==['Історичний стрілець','Сапер']
    assert result['note']=='Власна примітка'
    assert result['unknown_periods']==[{'from':D(2026,5,1),'to':D(2026,5,31)}]
    assert events_for_staff(store,versions[1].id,D(2026,8,1),D(2026,1,1),D(2026,9,1))==[event]


@pytest.mark.parametrize('key',['date_start','date_end','order_date'])
@pytest.mark.parametrize('raw',['15._.2026','_.03.2026','_._._','31.02.2026'])
def test_person_event_rejects_partial_and_invalid_dates(store,key,raw):
    with pytest.raises(ValueError):setattr(PersonEvent(),key,raw)


def test_event_required_start_and_optional_exact_end(store):
    with pytest.raises(ValueError):PersonEvent(date_start=None)
    event=PersonEvent(date_start=D(2026,1,1),date_end=None)
    assert event.date_end is None
    assert str(PersonEvent.__table__.c.date_end.type)=='DATE'
    assert str(PersonAssignment.__table__.c.assigned_from.type)=='DATE'
    from app.models.person_history_model import HistoryModel
    assert str(PersonName.__table__.c.created_at.type)=='DATETIME'


def test_selector_status_sorting_partial_birth_and_twins(store):
    _,versions,positions,people=setup(store)
    Service.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    result=person_options(store,D(2026,7,1))
    assert result[-1]['id']==people[0].person_id
    assert result[-1]['status']=='Призначений · посада № 15'
    assert result[-1]['birth']=='_.04.1998'
    assert result[-1]['rank']=='Солдат'
    assert sum(bool(item['disambiguation']) for item in result)==2
    assert all('tax' not in key for item in result for key in item)


def test_http_import_and_assignment_confirmation(store):
    _,versions,positions,people=setup(store)
    old=Service.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    def isolated():yield store
    app.dependency_overrides[get_db]=isolated
    try:
        with TestClient(app) as client:
            data={'position_id':positions[2].position_id,'person_id':people[0].person_id,'on':'2026-08-01'}
            preview=client.post('/person-positions/assign/prepare',data=data)
            assert preview.status_code==200 and preview.json()['requires_confirmation']
            token=preview.json()['token']
            assert client.post('/person-positions/assign',data={'token':token}).status_code==409
            assert store.get(PersonAssignment,old).assigned_to is None
            saved=client.post('/person-positions/assign',data={'token':token,'confirmed':'true'},follow_redirects=False)
            assert saved.status_code==303
            assert client.post('/person-positions/assign',data={'token':token,'confirmed':'true'}).status_code==409
            assert client.post('/person-positions/assign',data={'token':token+'bad','confirmed':'true'}).status_code==409
            response=client.post('/staff/import/preview',data={'name':'Архів 2025','valid_from':'2025-01-01','valid_to':'2025-12-31','structure_id':versions[0].staff_structure_id},files={'file':('staff.xlsx',workbook().getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
            assert response.status_code==200
            from lxml import html
            document=html.fromstring(response.text)
            import_token=document.xpath('//input[@name="token"]/@value')[0]
            before=store.query(StaffVersion).count()
            result=client.post('/staff/import/confirm',data={'token':import_token},follow_redirects=False)
            assert result.status_code==303 and store.query(StaffVersion).count()==before+1
            assert client.post('/staff/import/confirm',data={'token':import_token}).status_code==409
            assert client.get('/staff/history').status_code==200
    finally:app.dependency_overrides.clear()


def test_db_guards_direct_writes_and_concurrent_competitors(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'concurrent.sqlite'),connect_args={'timeout':3})
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        _,versions,positions,people=setup(db)
        target=positions[1].position_id;person_ids=[person.person_id for person in people[:2]]
    barrier=Barrier(2)
    def contender(person):
        with Session(engine) as db:
            snapshot=Service.assignment_snapshot(db,target,person,D(2026,8,1))
            barrier.wait()
            try:Service.assign(db,target,person,D(2026,8,1),snapshot);return 'ok'
            except ValueError:return 'conflict'
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(contender,person_ids))
    assert sorted(results)==['conflict','ok']
    with Session(engine) as db:
        assert db.query(PersonAssignment).count()==1
        with pytest.raises(IntegrityError):
            db.execute(text("INSERT INTO person_assignments(person_id,staff_position_id,assigned_from,revision,created_at,updated_at) VALUES (:person,:pos,'2026-08-01',1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"),{'person':person_ids[1],'pos':target});db.commit()
        db.rollback()
        with pytest.raises(IntegrityError):
            db.execute(text('DELETE FROM person_assignments'));db.commit()
    engine.dispose()


def test_event_service_can_create_backdated_event_without_any_assignment(store):
    from app.services.service_for_person_event import PersonEventService
    _,_,_,people=setup(store)
    kind=EventType(event_type='trip',event_name='Відрядження');store.add(kind);store.commit()
    person_id=people[0].person_id; kind_id=kind.event_type_id
    store.rollback()
    factory=lambda:Session(store.bind)
    created=PersonEventService.create_person_event(person_id,kind_id,date_start='01.02.2025',date_end='28.02.2025',note='Незалежна подія',session_factory=factory)
    assert created.date_start==D(2025,2,1)
    assert event_positions(store,store.get(PersonEvent,created.event_id))['position_status']=='Інформація про посаду відсутня'
    changed=PersonEventService.change_person_event(created.event_id,kind_id,date_start='02.02.2025',date_end='28.02.2025',session_factory=factory)
    assert changed.date_start==D(2025,2,2)
    with pytest.raises(ValueError):PersonEventService.create_person_event(person_id,kind_id,date_start='01._.2025',session_factory=factory)
    with pytest.raises(ValueError):PersonEventService.create_person_event(person_id,kind_id,date_start='01.03.2025',date_end='28.02.2025',session_factory=factory)
    assert store.query(PersonEvent).count()==1


def test_raw_partial_dates_are_rejected_even_without_orm(store):
    _,_,_,people=setup(store)
    kind=EventType(event_type='exact',event_name='Точна');store.add(kind);store.commit()
    for start,end in [('2026-01-01','2026-02-31'),('2026-01-__',None),('2026-02-02','2026-02-01')]:
        with pytest.raises(IntegrityError):
            store.execute(text('INSERT INTO person_events(person_id,event_type_id,date_start,date_end) VALUES (:person,:kind,:start,:end)'),{'person':people[0].person_id,'kind':kind.event_type_id,'start':start,'end':end})
            store.commit()
        store.rollback()

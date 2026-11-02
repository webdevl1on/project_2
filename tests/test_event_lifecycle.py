"""Event plans and clerical control, on disposable synthetic SQLite only."""
from datetime import date
import pytest
from sqlalchemy import select, func, event
from fastapi.testclient import TestClient
from app.models import Person, PersonEvent, EventType, EventSubtype
from app.models.medical import PersonnelTask
from app.services import person_events as editor, event_views, event_rules, service_for_person_event as core
from app.database.db import get_db
from tests.test_service_transactions import factory


@pytest.fixture
def lifecycle(factory, monkeypatch):
    on = date(2026,11,2)
    for module in (editor,event_views,event_rules,core): monkeypatch.setattr(module,'today',lambda: on)
    with factory.begin() as db:
        person=Person(sex='male');db.add(person)
        kinds={code:EventType(event_type=code,event_name=name) for code,name in [('SERVICE','Служба'),('VACATION','Відпустка'),('HOSPITAL','Лікарняний'),('BUSINESS_TRIP','Відрядження'),('VLK','ВЛК')]}
        db.add_all(kinds.values());db.flush()
        mission=EventSubtype(event_type_id=kinds['BUSINESS_TRIP'].event_type_id,event_subtype='BUSINESS_TRIP_MISSION',event_subtype_name='СБЗ');db.add(mission);db.flush()
        return factory,person.person_id,{k:v.event_type_id for k,v in kinds.items()},mission.event_subtype_id


def add(db, context, code='VACATION', **values):
    _,pid,kinds,_=context
    return editor.save(db,pid,{'event_type_id':kinds[code],'date_start':'2026-10-01',**values})


def record(db,pid,key):return next(r for r in editor.page(db,pid)['events'] if r['event_id']==key)


def test_planned_duration_is_not_actual_and_overdue_is_not_service(lifecycle):
    factory,pid,*_=lifecycle
    with factory() as db:
        key=add(db,lifecycle,planned_duration='10')
        row=db.get(PersonEvent,key)
        assert row.planned_end==date(2026,10,10) and row.date_end is row.duration is None
        assert not row.completion_confirmed
        assert event_views.presence_for_people(db,[pid],date(2026,10,10))[pid]['code']=='VACATION'
        assert event_views.presence_for_people(db,[pid],date(2026,10,11))[pid]['code']=='__pending__'
        assert event_views.presence_for_people(db,[pid],date(2026,9,30))[pid]['code']=='__base__'
        assert db.scalar(select(func.count()).select_from(PersonEvent))==1


@pytest.mark.parametrize('actual',['2026-10-09','2026-10-10','2026-10-12'])
def test_explicit_return_can_be_early_planned_or_late(lifecycle,actual):
    factory,pid,*_=lifecycle
    with factory() as db:
        key=add(db,lifecycle,planned_end='2026-10-10')
        original=record(db,pid,key)
        editor.save(db,pid,{**original,'date_end':actual,'completion_confirmed':'1'},key)
        row=db.get(PersonEvent,key)
        assert row.date_end==date.fromisoformat(actual) and row.completion_confirmed
        assert row.planned_end==date(2026,10,10) and row.duration==int(actual[-2:])
        assert event_views.problems(db)['items']==[]
        assert event_views.presence_for_people(db,[pid],date(2026,11,2))[pid]['calculated']


@pytest.mark.parametrize('code',['VACATION','HOSPITAL','BUSINESS_TRIP'])
def test_new_actual_event_cannot_implicitly_close_clerical_event(lifecycle,code):
    factory,pid,*_=lifecycle
    with factory() as db:
        key=add(db,lifecycle,code)
        with pytest.raises(editor.EventConflictError):add(db,lifecycle,'SERVICE',date_start='2026-10-15')
        assert db.get(PersonEvent,key).date_end is None
        assert db.scalar(select(func.count()).select_from(PersonEvent))==1


def test_future_plans_do_not_close_facts_and_conflict_is_exposed_on_arrival(lifecycle,monkeypatch):
    factory,pid,*_=lifecycle
    with factory() as db:
        old=add(db,lifecycle,planned_end='2026-10-10')
        plan=add(db,lifecycle,'BUSINESS_TRIP',date_start='2026-11-15',planned_end='2026-11-20')
        assert db.get(PersonEvent,old).date_end is None and record(db,pid,plan)['mirage']
        # Distinct later plans can coexist using their planned periods.
        add(db,lifecycle,'SERVICE',date_start='2026-11-21',planned_end='2026-11-22')
        for module in (editor,event_views,event_rules,core):monkeypatch.setattr(module,'today',lambda:date(2026,11,15))
        assert not record(db,pid,plan)['mirage']
        assert event_views.presence_for_people(db,[pid],date(2026,11,15))[pid]['code']=='__conflict__'
        assert db.get(PersonEvent,old).date_end is None


@pytest.mark.parametrize('values,field',[
    ({'planned_end':'_.10.2026'},'planned_end'),({'planned_end':'2026-09-30'},'planned_end'),
    ({'planned_duration':'0'},'planned_duration'),({'planned_end':'2026-10-05','planned_duration':'10'},'planned_duration'),
    ({'completion_confirmed':'1'},'date_end'),({'date_end':'2026-10-10','completion_confirmed':'0'},'completion_confirmed'),
    ({'date_end':'2026-11-15','completion_confirmed':'1'},'date_end'),({'completion_confirmed':'invalid'},'completion_confirmed')])
def test_invalid_new_fields_are_atomic(lifecycle,values,field):
    factory,pid,*_=lifecycle
    with factory() as db:
        with pytest.raises(ValueError) as error:add(db,lifecycle,**values)
        assert error.value.field==field
        assert db.scalar(select(func.count()).select_from(PersonEvent))==0


@pytest.mark.parametrize('code,start,planned,on,expected,overdue',[
    ('BUSINESS_TRIP','2026-10-01','2026-11-30','2026-11-09',None,False),
    ('BUSINESS_TRIP','2026-10-01','2026-11-30','2026-11-10','rotation',False),
    ('BUSINESS_TRIP','2026-10-01','2026-11-30','2026-12-01','rotation',True),
    ('VACATION','2026-10-01','2026-10-10','2026-10-10',None,False),
    ('VACATION','2026-10-01','2026-10-10','2026-10-11','vacation',True),
    ('HOSPITAL','2026-10-01',None,'2026-10-15',None,False),
    ('HOSPITAL','2026-10-01',None,'2026-10-16','hospital',False),
    ('VLK','2026-10-01',None,'2026-10-16','vlk',False)])
def test_problem_boundaries(lifecycle,code,start,planned,on,expected,overdue):
    factory,pid,kinds,mission=lifecycle
    with factory() as db:
        key=add(db,lifecycle,code,date_start=start,planned_end=planned,event_subtype_id=mission if code=='BUSINESS_TRIP' else None)
        result=event_rules.problem(record(db,pid,key),on=date.fromisoformat(on))
        assert (result['group'] if result else None)==expected
        if result:assert result['overdue']==overdue


def test_issue_refresh_is_readonly_unique_and_independent_of_medical_tasks(lifecycle):
    factory,pid,*_=lifecycle
    with factory() as db:
        key=add(db,lifecycle,planned_end='2026-10-10')
        task_count=db.scalar(select(func.count()).select_from(PersonnelTask))
        a=event_views.problems(db);b=event_views.problems(db)
        assert a==b and len(a['items'])==1 and a['items'][0]['id']==f'event:{key}'
        assert not db.new and not db.dirty
        original=record(db,pid,key)
        editor.save(db,pid,{**original,'planned_end':'2026-11-20'},key)
        assert event_views.problems(db)['items']==[]
        assert db.scalar(select(func.count()).select_from(PersonnelTask))==task_count
        medical_task=PersonnelTask(person_id=pid,title='Незалежне медичне питання',kind='manual',status='COMPLETED',manual_decision=True,decision_reason='Перевірено медиком')
        db.add(medical_task);db.commit();task_id=medical_task.id
        # Completing a medical task does not resolve this event's new overdue date.
        current=record(db,pid,key)
        editor.save(db,pid,{**current,'planned_end':'2026-10-10'},key)
        assert len(event_views.problems(db)['items'])==1
        medical_task=db.get(PersonnelTask,task_id);medical_task.status='OPEN';db.commit()
        current=record(db,pid,key)
        editor.save(db,pid,{**current,'date_end':'2026-10-10','completion_confirmed':'1'},key)
        assert event_views.problems(db)['items']==[]
        assert db.get(PersonnelTask,task_id).status=='OPEN'
        assert db.get(PersonnelTask,task_id).decision_reason=='Перевірено медиком'


def test_subtype_colour_and_computed_service_are_distinct(lifecycle):
    from app.event_display import event_presentation
    values={'type_code':'BUSINESS_TRIP','type_name':'Відрядження','type_color':'#123456','subtype_code':'BUSINESS_TRIP_MISSION','subtype_name':'СБЗ'}
    assert event_presentation(values)['background']!=event_presentation({**values,'subtype_code':None})['background']
    assert event_presentation(values)['subtype']=='СБЗ'
    assert event_presentation({**values,'type_color':'url(evil)'})['background'].startswith('#')
    assert 'accent_color' not in event_presentation({**values,'type_color':'url(evil)'})
    assert event_presentation({**values,'type_color':'teal'})['accent_color']=='teal'


def test_problem_page_uses_current_control_and_existing_modal(lifecycle):
    from app.main import app
    factory,pid,*_=lifecycle
    with factory() as db:add(db,lifecycle,planned_end='2026-10-10')
    def session():
        with factory() as db:yield db
    previous=app.dependency_overrides.copy();app.dependency_overrides[get_db]=session
    try:
        with TestClient(app) as client:
            response=client.get('/events/problems')
            assert response.status_code==200 and 'event:1' in response.text and '10.10.2026' in response.text
            assert 'Медичні рішення' in response.text
    finally:app.dependency_overrides.clear();app.dependency_overrides.update(previous)

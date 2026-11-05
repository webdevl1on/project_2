"""Read-only reference views on synthetic SQLite, separate from working data."""
from datetime import date
import pytest
from sqlalchemy import select,func
from tests.http_auth import AuthenticatedClient as TestClient
from app.models import PersonEvent,EventType,StaffVersion,Person
from app.database.db import get_db
from app.services import event_views,person_events
from app.services.staff_service import StaffService
from app.services.service_person_create import ServicePersonCreate
from app.services.service_person_positions import ServicePersonPositionFunc
from app.table_columns import PERSON_POSITIONS_FIELDS
from tests.test_service_transactions import factory,data
from tests.test_person_positions import make_position


@pytest.fixture
def views(factory):
    with factory() as db:
        types=list(db.scalars(select(EventType).order_by(EventType.event_type_id)))
        types[0].event_type='SERVICE';types[0].event_name='Служба'
        types[1].event_type='VACATION';types[1].event_name='Відпустка';db.commit()
        first=ServicePersonCreate.create_person(data(),db).person_id
        second=ServicePersonCreate.create_person(data(surname='Безштатний',tax_number='0123456788'),db).person_id
        structure=StaffService.create_structure(db,'journal','Тестова')
        version=StaffVersion(staff_structure_id=structure,name='Тест',valid_from=date(2026,1,1));db.add(version);db.flush()
        a=make_position(1,'1 взвод','Водій','Водій');b=make_position(2,'2 взвод','Медик','Медик')
        a.staff_version_id=b.staff_version_id=version.id;db.add_all([a,b]);db.commit()
        StaffService.create_assignment(db,first,a.position_id,date(2026,1,1))
        person_events.save(db,first,{'event_type_id':types[1].event_type_id,'date_start':'2026-10-01','date_end':'2026-10-03'})
        person_events.save(db,first,{'event_type_id':types[0].event_type_id,'date_start':'2026-10-04'})
        person_events.save(db,second,{'event_type_id':types[1].event_type_id,'date_start':'2026-10-02','date_end':'2026-10-02'})
        return factory,first,second,version.id,types[0].event_type_id,types[1].event_type_id


def test_inclusive_day_projection_and_open_event_do_not_write_dates(views):
    factory,pid,second,version,service,vacation=views
    with factory() as db:
        before=[(r.event_id,r.date_end,r.duration) for r in db.scalars(select(PersonEvent))]
        page=event_views.journal(db,{'start':'2026-10-01','end':'2026-10-07'})
        person=next(p for p in page['people'] if p['id']==pid)
        assert [c['label'] for c in person['cells']]==['відпустка']*3+['служба']*4
        counts={c['code']:c['days'] for c in person['summary']}
        assert counts['VACATION']==3 and counts['SERVICE']==4 and counts['__base__']==0
        assert sum(c['days'] for c in person['summary'])==7
        assert len(page['people'])==1
        assert all(p['id']!=second for p in page['people'])
        assert [(r.event_id,r.date_end,r.duration) for r in db.scalars(select(PersonEvent))]==before
        assert not db.new and not db.dirty


@pytest.mark.parametrize('scale,buckets',[('day',7),('week',2),('month',1)])
def test_scales_keep_identical_person_day_totals(views,scale,buckets):
    factory,pid,*_=views
    with factory() as db:
        page=event_views.journal(db,{'start':'2026-10-01','end':'2026-10-07','scale':scale})
        assert len(page['buckets'])==buckets
        person=next(p for p in page['people'] if p['id']==pid)
        assert sum(item['days'] for item in person['summary'])==7
        assert len(person['cells'])==buckets


def test_journal_filters_people_without_discarding_other_event_context(views):
    factory,pid,second,version,service,vacation=views
    with factory() as db:
        raw={'start':'2026-10-01','end':'2026-10-07','unit':'1 взвод','search':'тЕсТоВиЙ','event_type':str(vacation)}
        page=event_views.journal(db,raw)
        assert [p['id'] for p in page['people']]==[pid]
        assert {e['type_code'] for e in page['people'][0]['events']}=={'SERVICE','VACATION'}
        assert event_views.journal(db,{**raw,'search':'немаєзбігу'})['people']==[]


def test_staff_projection_has_one_row_and_distinguishes_vacancy_from_no_event(views):
    factory,pid,second,version,*_=views
    with factory() as db:
        early=ServicePersonPositionFunc.get_positions(db,version_id=version,on=date(2026,9,30))
        assert [r['values']['event_on_date'] for r in early['rows']]==['служба','вакантна']
        state=ServicePersonPositionFunc.get_positions(db,version_id=version,on=date(2026,10,3))
        assert len(state['rows'])==2 and state['rows'][0]['values']['event_on_date']=='відпустка'
        after=ServicePersonPositionFunc.get_positions(db,version_id=version,on=date(2026,10,4))
        assert after['rows'][0]['values']['event_on_date']=='служба'
        field=PERSON_POSITIONS_FIELDS['event_on_date']
        assert field.metadata()['source']['computed'] and not field.filterable and not field.sortable


def test_ambiguous_legacy_events_are_explicit_without_double_counting(views):
    factory,pid,second,version,service,vacation=views
    with factory.begin() as db:
        db.add(PersonEvent(person_id=pid,event_type_id=service,date_start=date(2026,10,2),date_end=date(2026,10,2),completion_confirmed=True))
    with factory() as db:
        page=event_views.journal(db,{'start':'2026-10-01','end':'2026-10-03'})
        person=next(p for p in page['people'] if p['id']==pid)
        assert person['cells'][1]['tone']=='conflict'
        assert sum(e['days'] for e in person['summary'])==3
        assert next(e for e in person['summary'] if e['code']=='__conflict__')['days']==1
        assert event_views.presence_for_people(db,[pid],date(2026,10,2))[pid]['tone']=='conflict'


@pytest.mark.parametrize('raw',[{'start':'2026-10-02','end':'2026-10-01'},{'start':'_.10.2026'},{'start':'2026-01-01','end':'2027-01-02'},{'scale':'bad'},{'event_type':'no'},{'sort':'sql;drop'},{'direction':'bad'}])
def test_invalid_journal_parameters_are_rejected(raw):
    with pytest.raises(ValueError):event_views.parse_options(raw)


def test_http_journal_and_read_only_refresh_endpoints(views):
    from app.main import app
    factory,pid,*_=views
    def session():
        with factory() as db:yield db
    previous=app.dependency_overrides.copy();app.dependency_overrides[get_db]=session
    try:
        with TestClient(app) as client:
            page=client.get('/events?start=2026-10-01&end=2026-10-07')
            assert page.status_code==200 and 'event-journal-data' in page.text
            assert page.headers['cache-control']=='no-store'
            assert client.get('/events/data?start=2026-10-01&end=2026-10-07').json()['people']
            assert client.get(f'/events/presence?person_id={pid}&on=2026-10-03').json()['label']=='відпустка'
            assert client.get('/events?start=bad').status_code==422
    finally:
        app.dependency_overrides.clear();app.dependency_overrides.update(previous)

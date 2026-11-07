"""Intentional corrections and preserved annulments on isolated synthetic data."""
from datetime import date
import pytest
from tests.http_auth import AuthenticatedClient as TestClient
from sqlalchemy import select, func, event, text
from app.models import PersonEvent, PersonEventCorrection, User, UserSession
from app.services import person_events as editor, event_views
from app.services.service_for_person_event import PersonEventService
from app.database.db import get_db
from tests.test_service_transactions import factory
from tests.test_event_lifecycle import lifecycle, add, record
from tests.test_event_views import views


def count(db,model):return db.scalar(select(func.count()).select_from(model))


def test_type_change_requires_server_intent_and_keeps_id_and_history(lifecycle):
    factory,pid,kinds,_=lifecycle
    with factory() as db:
        key=add(db,lifecycle,planned_end='2026-10-10')
        original=record(db,pid,key)
        with pytest.raises(ValueError,match='Підтвердьте'):
            editor.save(db,pid,{**original,'event_type_id':kinds['BUSINESS_TRIP']},key)
        assert db.get(PersonEvent,key).event_type_id==kinds['VACATION'] and count(db,PersonEventCorrection)==0
        editor.save(db,pid,{**original,'event_type_id':kinds['BUSINESS_TRIP'],'confirm_type_change':'1'},key)
        assert db.get(PersonEvent,key).event_type_id==kinds['BUSINESS_TRIP'] and count(db,PersonEvent)==1
        history=editor.page(db,pid)['events'][0]['corrections']
        assert len(history)==1 and history[0]['operation']=='type_change' and history[0]['actor_id'] is None
        assert history[0]['before']['event_type_id']==kinds['VACATION'] and history[0]['after']['event_type_id']==kinds['BUSINESS_TRIP']
        assert history[0]['occurred_at'].endswith('+00:00')
        # The core service also prevents bypassing explicit intent.
        with pytest.raises(ValueError,match='Підтвердьте'):
            PersonEventService.change_person_event(key,kinds['VACATION'],date_start=date(2026,10,1),db=db)


def test_incompatible_subtype_and_stale_form_never_leave_a_correction(lifecycle):
    factory,pid,kinds,mission=lifecycle
    with factory() as db:
        key=add(db,lifecycle,'BUSINESS_TRIP',event_subtype_id=mission)
        original=record(db,pid,key)
        with pytest.raises(ValueError,match='не належить'):
            editor.save(db,pid,{**original,'event_type_id':kinds['VACATION'],'confirm_type_change':'1'},key)
        assert count(db,PersonEventCorrection)==0
        editor.save(db,pid,{**original,'note':'Уточнено'},key)
        with pytest.raises(editor.EventConflictError):editor.save(db,pid,{**original,'event_type_id':kinds['VACATION'],'event_subtype_id':'','confirm_type_change':'1'},key)
        assert count(db,PersonEventCorrection)==0


@pytest.mark.parametrize('reason',['','   ','x'*2001])
def test_annulment_requires_meaningful_bounded_reason(lifecycle,reason):
    factory,pid,*_=lifecycle
    with factory() as db:
        key=add(db,lifecycle);original=record(db,pid,key)
        with pytest.raises(ValueError):editor.annul(db,pid,key,{'expected_state':original['expected_state'],'reason':reason})
        assert db.get(PersonEvent,key).annulled_at is None and count(db,PersonEventCorrection)==0


def test_annulment_preserves_data_excludes_all_projections_and_conflicts(lifecycle):
    factory,pid,*_=lifecycle
    with factory() as db:
        key=add(db,lifecycle,planned_end='2026-10-10');original=record(db,pid,key)
        assert len(event_views.problems(db)['items'])==1
        editor.annul(db,pid,key,{'expected_state':original['expected_state'],'reason':'Помилковий запис'})
        row=db.get(PersonEvent,key)
        assert row.event_id==key and row.date_start==date(2026,10,1) and row.planned_end==date(2026,10,10)
        assert row.date_end is None and not row.completion_confirmed
        assert row.annulment_reason=='Помилковий запис' and row.annulled_by is None
        assert event_views.problems(db)['items']==[]
        assert event_views.presence_for_people(db,[pid],date(2026,11,2))[pid]['calculated']
        page=editor.page(db,pid);assert page['events']==[] and len(page['annulled'])==1
        assert page['annulled'][0]['corrections'][0]['operation']=='annul'
        view=event_views.journal(db,{'start':'2026-10-01','end':'2026-10-02'})
        assert view['people']==[] # This person has no official assignment; editor archive above remains accessible.
        add(db,lifecycle,'SERVICE') # identical date now accepted, old event remains archived
        assert count(db,PersonEvent)==2
        with pytest.raises(ValueError):editor.save(db,pid,{**page['annulled'][0],'note':'rewrite'},key)
        with pytest.raises(editor.EventConflictError):editor.annul(db,pid,key,{'expected_state':original['expected_state'],'reason':'double'})
        assert count(db,PersonEventCorrection)==1


def test_annulment_does_not_confirm_or_close_other_events(lifecycle):
    factory,pid,*_=lifecycle
    with factory() as db:
        actual=add(db,lifecycle,planned_end='2026-10-10')
        plan=add(db,lifecycle,'SERVICE',date_start='2099-01-01')
        value=record(db,pid,plan)
        editor.annul(db,pid,plan,{'expected_state':value['expected_state'],'reason':'План скасовано'})
        assert db.get(PersonEvent,actual).date_end is None and not db.get(PersonEvent,actual).completion_confirmed
        assert len(event_views.problems(db)['items'])==1


@pytest.mark.parametrize('operation',['type_change','annul'])
def test_failed_audit_write_rolls_back_business_record(lifecycle,operation):
    factory,pid,kinds,_=lifecycle
    with factory() as db:
        key=add(db,lifecycle);original=record(db,pid,key)
        def refuse(*args):raise RuntimeError('synthetic audit refusal')
        event.listen(PersonEventCorrection,'before_insert',refuse)
        try:
            with pytest.raises(RuntimeError):
                if operation=='annul':editor.annul(db,pid,key,{'expected_state':original['expected_state'],'reason':'Тест'})
                else:editor.save(db,pid,{**original,'event_type_id':kinds['SERVICE'],'confirm_type_change':'1'},key)
        finally:event.remove(PersonEventCorrection,'before_insert',refuse)
        assert record(db,pid,key)['expected_state']==original['expected_state']
        assert count(db,PersonEventCorrection)==0


def test_http_cannot_forge_actor_or_delete_and_records_authenticated_actor(lifecycle):
    from app.main import app
    from app.services.accounts import password_hash
    from tests.mfa_helpers import login
    factory,pid,kinds,_=lifecycle
    with factory() as db:
        user=User(username='event-test',display_name='Тестовий автор',password_hash=password_hash('synthetic-password'),role='editor');db.add(user);db.commit();actor=user.id
        token,csrf=login(db,'event-test','synthetic-password')
        key=add(db,lifecycle);original=record(db,pid,key)
    def session():
        with factory() as db:yield db
    previous=app.dependency_overrides.copy();app.dependency_overrides[get_db]=session
    try:
        with TestClient(app) as client:
            base=f'/persons/{pid}/events/{key}'
            assert client.delete(base).status_code==405
            assert client.post(base,data={**original,'event_type_id':kinds['SERVICE']}).status_code==422
            client.cookies.clear();client.cookies.set('project2_user',token);client.headers['X-CSRF-Token']=csrf
            response=client.post(base,data={**original,'event_type_id':kinds['SERVICE'],'confirm_type_change':'1','actor_id':99999})
            assert response.status_code==200
            current=client.get(f'/persons/{pid}/events').json()['events'][0]
            assert current['corrections'][0]['actor_id']==actor
            assert client.post(base+'/annul',headers={'Origin':'https://foreign.invalid'},data={'reason':'test'}).status_code==403
    finally:app.dependency_overrides.clear();app.dependency_overrides.update(previous)


@pytest.mark.parametrize('sort',['name','unit','position_number','position_short','date:2026-10-02:2026-10-02','date:2026-10-01:2026-10-07'])
@pytest.mark.parametrize('direction',['asc','desc'])
def test_supported_sort_keys_for_snapshot_staff(views,sort,direction):
    factory,pid,second,*_=views
    with factory() as db:
        from app.models import Position
        from app.services.staff_service import StaffService
        position=db.scalar(select(Position).where(Position.position_number==2))
        StaffService.create_assignment(db,second,position.position_id,date(2026,1,1))
        result=event_views.journal(db,{'start':'2026-10-01','end':'2026-10-07','sort':sort,'direction':direction})
        assert len(result['people'])==2 and result['options']['sort']==sort and result['options']['direction']==direction
        if sort in ('position_number','position_short'):assert [p['id'] for p in result['people']]==([pid,second] if direction=='asc' else [second,pid])
        if sort=='name':assert [p['id'] for p in result['people']]==([second,pid] if direction=='asc' else [pid,second])


def test_date_sort_survives_period_change_without_changing_daily_totals(views):
    factory,pid,second,*_=views
    with factory() as db:
        from app.models import Position
        from app.services.staff_service import StaffService
        position=db.scalar(select(Position).where(Position.position_number==2))
        StaffService.create_assignment(db,second,position.position_id,date(2026,1,1))
        # On Oct 1 only pid is on vacation; the other person has base service.
        result=event_views.journal(db,{'start':'2026-09-01','end':'2026-09-02','sort':'date:2026-10-01:2026-10-01'})
        assert [p['id'] for p in result['people']]==[pid,second]
        assert all(sum(e['days'] for e in p['summary'])==2 for p in result['people'])
        assert all(all(c['calculated'] for c in p['cells']) for p in result['people'])

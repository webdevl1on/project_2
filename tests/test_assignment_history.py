"""Assignment history, author attribution and rollback on isolated SQLite."""
from tests.access_helpers import legacy_user
from tests.mfa_helpers import login as mfa_login
from datetime import date as D, timedelta
import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from fastapi.testclient import TestClient
from lxml import html
from app.models import PersonAssignment, AssignmentAudit, Position, StaffVersion
from app.services.staff_service import StaffService as Service, assignments_at
from app.services.staff_read import history_context
from app.services import staff_service, accounts, mirage
from app.main import app
from app.database.db import get_db
from tests.test_staff_history import store, setup


@pytest.fixture
def data(store, monkeypatch):
    monkeypatch.setattr(staff_service, 'today', lambda:D(2026,11,3))
    return (store, *setup(store))


def create(data, *, end=None, start=D(2026,6,1), person=0, pos=1, **kw):
    db,_,_,positions,people=data
    return Service.create_assignment(db,people[person].person_id,positions[pos].position_id,start,end,**kw)


def test_create_edit_orders_and_exit_have_separate_audits(data):
    db,_,_,positions,people=data
    key=create(data,order_number='125',order_date=D(2030,1,1))
    record=db.get(PersonAssignment,key)
    Service.correct_assignment(db,key,record.revision,record.person_id,record.staff_position_id,record.assigned_from,D(2026,9,1),details={
        'assignment_order_number':'125/1','assignment_order_date':D(2026,5,31),'release_order_number':'205',
        'release_order_date':D(2026,8,31),'completion_reason':'transfer','completion_note':'До іншого підрозділу поза штатом'})
    assert db.query(PersonAssignment).count()==1
    Service.correct_orders(db,key,record.revision,assignment_number='125/2')
    audits=db.query(AssignmentAudit).order_by(AssignmentAudit.id).all()
    assert [a.operation for a in audits]==['create','edit','orders']
    assert audits[1].before['assignment_order_number']=='125' and audits[1].after['assignment_order_number']=='125/1'
    assert all(a.actor_user_id is None for a in audits)
    assert record.completion_note=='До іншого підрозділу поза штатом'


def test_annul_excluded_from_every_actual_read_and_restore_same_id(data):
    db,_,versions,positions,people=data
    key=create(data);record=db.get(PersonAssignment,key);revision=record.revision
    Service.annul_assignment(db,key,revision,'Помилкове призначення',confirmed=True)
    assert db.get(PersonAssignment,key).annulled_at
    assert assignments_at(db,D(2026,7,1)).count()==0
    from app.repositories.person_repository import PersonRepository, ProfileRepository
    from app.repositories.staff_repository import StaffRepository
    assert not ProfileRepository.assignments(db,people[0].person_id)
    assert not StaffRepository.assignment_period_rows(db,people[0].person_id,D(2026,6,1),None)
    options=PersonRepository.picker_rows(db,D(2026,7,1),official_only=True)
    assert not options
    groups=history_context(db,versions[1].id)['position_groups']
    group=next(g for g in groups if g['position'].position_id==positions[1].position_id)
    assert len(group['annulled'])==1 and not group['current']
    Service.restore_assignment(db,key,record.revision)
    assert assignments_at(db,D(2026,7,1)).one().id==key
    Service.annul_assignment(db,key,record.revision,'Друга причина',confirmed=True)
    assert [a.operation for a in db.query(AssignmentAudit).order_by(AssignmentAudit.id)]==['create','annul','restore','annul']
    assert db.query(PersonAssignment).count()==1


def test_annul_reason_confirmation_revision_and_restore_conflict(data):
    db,*_=data;key=create(data);record=db.get(PersonAssignment,key)
    for reason,confirmed,revision in [('',True,record.revision),('x'*2001,True,record.revision),('тест',False,record.revision),('тест',True,999)]:
        with pytest.raises(ValueError):Service.annul_assignment(db,key,revision,reason,confirmed=confirmed)
    Service.annul_assignment(db,key,record.revision,'Помилка',confirmed=True)
    second=create(data,person=1)
    with pytest.raises(ValueError,match='перетинаються'):Service.restore_assignment(db,key,record.revision)
    assert db.get(PersonAssignment,key).annulled_at and db.get(PersonAssignment,second).annulled_at is None
    assert db.query(AssignmentAudit).count()==3
    with pytest.raises(ValueError,match='анульоване'):Service.correct_orders(db,key,record.revision,assignment_number='bad')


def test_edit_conflict_and_stale_revision_never_shift_other_assignment(data):
    db,*_=data
    first=create(data,end=D(2026,7,31));second=create(data,person=1,start=D(2026,8,1))
    record=db.get(PersonAssignment,first);before=record.revision
    with pytest.raises(ValueError,match='перетинаються'):
        Service.correct_assignment(db,first,before,record.person_id,record.staff_position_id,record.assigned_from,D(2026,8,5))
    assert db.get(PersonAssignment,first).assigned_to==D(2026,7,31)
    assert db.get(PersonAssignment,second).assigned_from==D(2026,8,1)
    Service.correct_orders(db,first,before,assignment_number='new')
    with pytest.raises(ValueError,match='змінився'):Service.correct_orders(db,first,before,assignment_number='stale')
    assert db.query(AssignmentAudit).count()==3


@pytest.mark.parametrize('offset',[-1,0,1,2,90])
def test_official_start_bound_service_and_http(data,offset):
    db,_,_,positions,people=data;start=D(2026,11,3)+timedelta(days=offset)
    if offset>1:
        with pytest.raises(ValueError,match='завтра'):create(data,start=start)
        with pytest.raises(ValueError,match='завтра'):Service.assignment_snapshot(db,positions[1].position_id,people[0].person_id,start)
        def override():yield db
        app.dependency_overrides[get_db]=override
        try:
            from tests.http_auth import AuthenticatedClient
            with AuthenticatedClient(app) as client:
                result=client.post('/staff/assignments/create',data={'person_id':people[0].person_id,'position_id':positions[1].position_id,'assigned_from':start.isoformat()},headers={'Accept':'application/json'})
                assert result.status_code==409 and 'завтра' in result.json()['detail']
        finally:app.dependency_overrides.clear()
        assert db.query(PersonAssignment).count()==db.query(AssignmentAudit).count()==0
    else:assert create(data,start=start)


def test_old_future_start_unchanged_allowed_but_cannot_move_further(data):
    db,_,_,positions,people=data
    record=PersonAssignment(person_id=people[0].person_id,staff_position_id=positions[1].position_id,assigned_from=D(2027,1,1))
    db.add(record);db.commit()  # synthetic legacy row predates the new service policy
    Service.correct_assignment(db,record.id,record.revision,record.person_id,record.staff_position_id,record.assigned_from,None,details={'assignment_order_number':'legacy'})
    assert record.assignment_order_number=='legacy'
    with pytest.raises(ValueError,match='завтра'):Service.correct_assignment(db,record.id,record.revision,record.person_id,record.staff_position_id,D(2027,1,2),None)
    assert db.query(AssignmentAudit).count()==1


def test_transfer_has_two_atomic_audits_and_does_not_cascade_annul(data):
    db,_,_,positions,people=data;old=create(data)
    on=D(2026,8,1)
    orders={'number':'125','date':'2026-07-31','release_number':'125','release_date':'2026-07-31'}
    snapshot=Service.assignment_snapshot(db,positions[2].position_id,people[0].person_id,on,orders)
    with pytest.raises(ValueError):Service.assign(db,positions[2].position_id,people[0].person_id,on,snapshot)
    Service.assign(db,positions[2].position_id,people[0].person_id,on,snapshot,True)
    previous=db.get(PersonAssignment,old);new=assignments_at(db,on).one()
    assert previous.assigned_to==D(2026,7,31) and previous.release_order_number=='125'
    assert new.assignment_order_number=='125'
    assert [a.operation for a in db.query(AssignmentAudit).order_by(AssignmentAudit.id)]==['create','complete','transfer']
    Service.annul_assignment(db,old,previous.revision,'Помилковий старий запис',confirmed=True)
    assert assignments_at(db,on).one().id==new.id


def test_mirage_conversion_cannot_bypass_future_limit(data):
    db,_,_,positions,people=data
    key=mirage.create(db,people[0].person_id,positions[2].position_id)
    from app.models import PersonPositionMirage
    with pytest.raises(ValueError,match='завтра'):mirage.preview(db,key,db.get(PersonPositionMirage,key).revision,D(2026,11,5))
    assert db.get(PersonPositionMirage,key).status=='waiting' and not db.query(PersonAssignment).count()


@pytest.mark.parametrize('action',['create','orders','annul','restore','transfer','close'])
def test_audit_failure_rolls_back_whole_business_operation(data,action):
    db,_,versions,positions,people=data
    key=create(data);record=db.get(PersonAssignment,key)
    if action=='restore':Service.annul_assignment(db,key,record.revision,'Помилка',confirmed=True)
    count=db.query(AssignmentAudit).count();revision=record.revision
    def refuse(*args):raise RuntimeError('synthetic audit failure')
    event.listen(AssignmentAudit,'before_insert',refuse)
    try:
        with pytest.raises(RuntimeError,match='audit failure'):
            if action=='create':create(data,person=1,pos=2)
            elif action=='orders':Service.correct_orders(db,key,revision,assignment_number='refused')
            elif action=='annul':Service.annul_assignment(db,key,revision,'Помилка',confirmed=True)
            elif action=='restore':Service.restore_assignment(db,key,revision)
            elif action=='close':Service.close_version(db,versions[1].id,versions[1].revision,D(2026,10,1))
            else:
                on=D(2026,8,1);snapshot=Service.assignment_snapshot(db,positions[2].position_id,people[0].person_id,on)
                Service.assign(db,positions[2].position_id,people[0].person_id,on,snapshot,True)
    finally:event.remove(AssignmentAudit,'before_insert',refuse)
    assert db.query(AssignmentAudit).count()==count and db.query(PersonAssignment).count()==1
    record=db.get(PersonAssignment,key);assert record.revision==revision and record.assigned_to is None
    assert bool(record.annulled_at)==(action=='restore')


def test_audit_is_append_only_and_assignment_not_deletable(data):
    db,*_=data;key=create(data)
    for sql in ["UPDATE assignment_audit SET reason='rewrite'",'DELETE FROM assignment_audit','DELETE FROM person_assignments']:
        with pytest.raises(DBAPIError):db.execute(text(sql));db.commit()
        db.rollback()
    assert db.query(AssignmentAudit).count()==db.query(PersonAssignment).count()==1


def test_history_search_vacancies_versions_and_constant_query_count(data):
    db,_,versions,positions,people=data
    create(data,end=D(2026,7,1));create(data,person=1,start=D(2026,8,1))
    context=history_context(db,versions[1].id)
    assert len(context['position_groups'])==2
    group=next(g for g in context['position_groups'] if g['position'].position_id==positions[1].position_id)
    assert len(group['archive'])==len(group['current'])==1
    assert len(history_context(db,versions[1].id,search='27')['position_groups'])==1
    assert len(history_context(db,versions[1].id,search='сАПЕР')['position_groups'])==1
    assert not history_context(db,versions[1].id,search='Історичний')['position_groups']
    queries=[]
    def count(*args):queries.append(args[2])
    event.listen(db.bind,'before_cursor_execute',count)
    try:history_context(db,versions[1].id)
    finally:event.remove(db.bind,'before_cursor_execute',count)
    assert len(queries)<=6


def test_two_personal_authors_body_spoof_ignored_and_anonymous_null(data):
    db,_,_,positions,people=data
    a=legacy_user(db,'author_a','Автор А','synthetic-password','admin')
    b=legacy_user(db,'author_b','Автор Б','synthetic-password','editor',actor_id=a)
    token_a,csrf_a=mfa_login(db,'author_a','synthetic-password');token_b,csrf_b=mfa_login(db,'author_b','synthetic-password')
    def override():yield db
    app.dependency_overrides[get_db]=override
    try:
        with TestClient(app,base_url='https://testserver') as client:
            client.cookies.set('project2_user',token_a);client.headers['X-CSRF-Token']=csrf_a
            result=client.post('/staff/assignments/create',data={'person_id':people[0].person_id,'position_id':positions[1].position_id,'assigned_from':'2026-06-01','actor_user_id':b},follow_redirects=False)
            assert result.status_code==303
            record=db.query(PersonAssignment).one();key=record.id
            client.cookies.clear();client.cookies.set('project2_user',token_b);client.headers['X-CSRF-Token']=csrf_b
            result=client.post(f'/personnel/assignments/{key}/orders',data={'revision':record.revision,'assignment_order_number':'125','actor_user_id':a})
            assert result.status_code==200
            client.cookies.clear()
            result=client.post(f'/personnel/assignments/{key}/orders',data={'revision':record.revision,'assignment_order_number':'125/1','actor_user_id':a})
            assert result.status_code==401
            audits=db.query(AssignmentAudit).order_by(AssignmentAudit.id).all()
            assert [x.actor_user_id for x in audits]==[a,b]
            assert audits[1].after['assignment_order_number']=='125'
            client.cookies.set('project2_user',token_a)
            view=client.get(f'/staff/assignments/{key}/audit')
            assert 'Автор А' in view.text and 'Автор Б' in view.text and 'Автор невідомий' not in view.text
            assert '01.06.2026' in view.text
            page=html.fromstring(client.get('/staff/history').text)
            assert len(page.xpath('//*[@data-person-picker]'))==1
            assert not page.xpath('//details[@data-position-id and @open]')
    finally:app.dependency_overrides.clear()


def test_end_and_order_dates_not_limited_and_release_has_own_audit(data):
    db,*_=data
    key=create(data,end=D(2035,1,1),order_date=D(2030,1,1))
    record=db.get(PersonAssignment,key)
    Service.release_assignment(db,key,record.revision,D(2026,8,1),'900',D(2031,1,1),'Поза нашим штатом',True)
    assert record.assigned_to==D(2026,7,31) and record.release_order_date==D(2031,1,1)
    assert db.query(PersonAssignment).count()==1
    assert [entry.operation for entry in db.query(AssignmentAudit).order_by(AssignmentAudit.id)]==['create','complete']


def test_restore_rechecks_changed_version_bounds(data):
    db,_,versions,_,_=data
    key=create(data);record=db.get(PersonAssignment,key)
    Service.annul_assignment(db,key,record.revision,'Помилка',confirmed=True)
    # Annulled records no longer block actual version corrections.
    version=versions[1]
    Service.correct_version(db,version.id,version.revision,version.name,D(2026,7,1),None)
    with pytest.raises(ValueError,match='період версії'):Service.restore_assignment(db,key,record.revision)
    assert db.get(PersonAssignment,key).annulled_at
    assert db.query(AssignmentAudit).count()==2


def test_direct_mirage_conversion_and_signed_assign_recheck_future_start(data):
    from app.models import PersonPositionMirage
    db,_,_,positions,people=data
    key=mirage.create(db,people[0].person_id,positions[2].position_id)
    expected=mirage.preview(db,key,db.get(PersonPositionMirage,key).revision,D(2026,11,4))
    # Even a trusted, previously prepared token must pass the current server clock.
    expected['snapshot']['on']='2026-11-05'
    with pytest.raises(ValueError,match='завтра'):mirage.convert(db,expected,True)
    with pytest.raises(ValueError,match='завтра'):Service.assign(db,positions[2].position_id,people[0].person_id,D(2026,11,5),expected['snapshot'],True)
    assert db.get(PersonPositionMirage,key).status=='waiting'
    assert db.query(PersonAssignment).count()==db.query(AssignmentAudit).count()==0

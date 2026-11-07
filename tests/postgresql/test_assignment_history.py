from tests.mfa_helpers import login as mfa_login
"""Actual PostgreSQL 17: additive migration, exclusion predicates, audit races."""
from datetime import date as D
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
import pytest
from sqlalchemy import text, select, func, event
from sqlalchemy.exc import DBAPIError
from alembic import command
from alembic.config import Config
from app.models import PersonAssignment, AssignmentAudit
from app.services.staff_service import StaffService as Service, assignments_at
from app.database.postgresql import require_postgresql_schema
from tests.test_staff_history import setup


@pytest.mark.parametrize('pg_factory',['0004_event_catalog'],indirect=True)
def test_additive_assignment_migration_preserves_old_orders_without_fake_audit(pg_factory):
    engine=pg_factory.kw['bind']
    with pg_factory() as db:
        _,versions,positions,people=setup(db)
        db.execute(text("INSERT INTO person_assignments(person_id,staff_position_id,assigned_from,assignment_order_number,assignment_order_date,created_at,updated_at,revision) VALUES (:person,:pos,'2026-06-01','125','2026-05-31',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"),{'person':people[0].person_id,'pos':positions[1].position_id})
        db.execute(text("INSERT INTO person_assignments(person_id,staff_position_id,assigned_from,assignment_order_number,created_at,updated_at,revision) VALUES (:person,:pos,'2027-01-01','legacy future',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"),{'person':people[1].person_id,'pos':positions[2].position_id});db.commit()
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with engine.begin() as db:
        cfg.attributes['connection']=db;command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    require_postgresql_schema(engine)
    with pg_factory() as db:
        row=db.scalar(select(PersonAssignment))
        assert row.assignment_order_number=='125' and row.assignment_order_date==D(2026,5,31)
        assert row.annulled_at is row.annulment_reason is row.annulled_by is None
        assert db.scalar(select(func.count()).select_from(AssignmentAudit))==0
        assert db.scalar(select(func.count()).select_from(PersonAssignment))==2
        legacy=db.scalar(select(PersonAssignment).where(PersonAssignment.assignment_order_number=='legacy future'))
        assert legacy.assigned_from==D(2027,1,1) and legacy.annulled_at is None


def test_annul_restore_exclusion_and_append_only_guards(pg_factory):
    engine=pg_factory.kw['bind']
    with pg_factory() as db:
        _,_,positions,people=setup(db)
        key=Service.create_assignment(db,people[0].person_id,positions[1].position_id,D(2026,6,1))
        row=db.get(PersonAssignment,key);Service.annul_assignment(db,key,row.revision,'Помилка',confirmed=True)
        assert assignments_at(db,D(2026,8,1)).count()==0
        newer=Service.create_assignment(db,people[1].person_id,positions[1].position_id,D(2026,6,1))
        with pytest.raises(ValueError,match='перетинаються'):Service.restore_assignment(db,key,row.revision)
        assert db.get(PersonAssignment,key).annulled_at
        Service.annul_assignment(db,newer,db.get(PersonAssignment,newer).revision,'Помилка другого запису',confirmed=True)
        Service.restore_assignment(db,key,row.revision)
        assert assignments_at(db,D(2026,8,1)).one().id==key
        Service.annul_assignment(db,key,row.revision,'Повторне анулювання',confirmed=True)
    for sql in ['DELETE FROM assignment_audit',"UPDATE assignment_audit SET reason='rewrite'",'DELETE FROM person_assignments',"UPDATE person_assignments SET completion_note='changed' WHERE id=:id"]:
        with pytest.raises(DBAPIError),engine.begin() as db:db.execute(text(sql),{'id':key})
    with pg_factory() as db:assert db.scalar(select(func.count()).select_from(AssignmentAudit))==6


def test_postgresql_audit_failure_rolls_back_transfer(pg_factory):
    with pg_factory() as db:
        _,_,positions,people=setup(db)
        key=Service.create_assignment(db,people[0].person_id,positions[1].position_id,D(2026,6,1))
        snapshot=Service.assignment_snapshot(db,positions[2].position_id,people[0].person_id,D(2026,8,1))
        calls=[]
        def refuse_second(*args):
            calls.append(True)
            if len(calls)==2:raise RuntimeError('second audit refused')
        event.listen(AssignmentAudit,'before_insert',refuse_second)
        try:
            with pytest.raises(RuntimeError):Service.assign(db,positions[2].position_id,people[0].person_id,D(2026,8,1),snapshot,True)
        finally:event.remove(AssignmentAudit,'before_insert',refuse_second)
        assert db.get(PersonAssignment,key).assigned_to is None
        assert db.scalar(select(func.count()).select_from(PersonAssignment))==1
        assert db.scalar(select(func.count()).select_from(AssignmentAudit))==1


def test_concurrent_edit_annul_revision_and_audit_not_lost(pg_factory):
    with pg_factory() as db:
        _,_,positions,people=setup(db)
        key=Service.create_assignment(db,people[0].person_id,positions[1].position_id,D(2026,6,1))
        revision=db.get(PersonAssignment,key).revision
    barrier=Barrier(2)
    def write(op):
        with pg_factory() as db:
            barrier.wait(timeout=5)
            try:
                if op=='edit':Service.correct_orders(db,key,revision,assignment_number='edited')
                else:Service.annul_assignment(db,key,revision,'Помилка',confirmed=True)
                return 200
            except ValueError:return 409
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(write,['edit','annul']))==[200,409]
    with pg_factory() as db:
        assert db.get(PersonAssignment,key).revision==revision+1
        assert db.scalar(select(func.count()).select_from(AssignmentAudit))==2


def test_postgresql_two_real_cookie_authors_and_unknown_actor(pg_factory,monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app.database.db import get_db
    from app.services import accounts
    with pg_factory() as db:
        _,_,positions,people=setup(db)
        pid,pos=people[0].person_id,positions[1].position_id
        a=accounts.create_user(db,'author_one','Автор один','synthetic-password','admin')
        b=accounts.create_user(db,'author_two','Автор два','synthetic-password','editor',actor_id=a)
        first,csrf_a=mfa_login(db,'author_one','synthetic-password');second,csrf_b=mfa_login(db,'author_two','synthetic-password')
    def override():
        with pg_factory() as db:yield db
    app.dependency_overrides[get_db]=override
    try:
        with TestClient(app,base_url='https://testserver') as client:
            client.cookies.set('project2_user',first);client.headers['X-CSRF-Token']=csrf_a
            result=client.post('/staff/assignments/create',data={'person_id':pid,'position_id':pos,'assigned_from':'2026-06-01','actor_user_id':b},follow_redirects=False)
            assert result.status_code==303
            with pg_factory() as db:row=db.scalar(select(PersonAssignment));key,rev=row.id,row.revision
            client.cookies.clear();client.cookies.set('project2_user',second);client.headers['X-CSRF-Token']=csrf_b
            assert client.post(f'/personnel/assignments/{key}/orders',data={'revision':rev,'assignment_order_number':'125','actor_user_id':a}).status_code==200
            with pg_factory() as db:rev=db.get(PersonAssignment,key).revision
            client.cookies.clear()
            assert client.post(f'/personnel/assignments/{key}/orders',data={'revision':rev,'assignment_order_number':'125/1','actor_user_id':a}).status_code==401
            client.cookies.set('project2_user',first)
            content=client.get(f'/staff/assignments/{key}/audit').text
            assert all(name in content for name in ['Автор один','Автор два'])
    finally:app.dependency_overrides.clear()
    with pg_factory() as db:
        assert [r.actor_user_id for r in db.scalars(select(AssignmentAudit).order_by(AssignmentAudit.id))]==[a,b]


def test_postgresql_official_future_boundary_and_unlimited_order_dates(pg_factory,monkeypatch):
    from app.services import staff_service
    monkeypatch.setattr(staff_service,'today',lambda:D(2026,11,3))
    with pg_factory() as db:
        _,_,positions,people=setup(db)
        with pytest.raises(ValueError,match='завтра'):Service.create_assignment(db,people[0].person_id,positions[1].position_id,D(2026,11,5))
        key=Service.create_assignment(db,people[0].person_id,positions[1].position_id,D(2026,11,4),D(2035,1,1),order_date=D(2030,1,1))
        row=db.get(PersonAssignment,key)
        assert row.assignment_order_date==D(2030,1,1)
        with pytest.raises(ValueError,match='завтра'):Service.correct_assignment(db,key,row.revision,row.person_id,row.staff_position_id,D(2026,11,5),row.assigned_to)
        assert db.scalar(select(func.count()).select_from(AssignmentAudit))==1

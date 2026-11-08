"""Real PostgreSQL 17 migration and concurrent account invariant checks, CI only."""
from tests.access_helpers import legacy_user
from tests.mfa_helpers import login as mfa_login
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
import pytest
from sqlalchemy import text,select,func,event
from sqlalchemy.exc import DBAPIError
from alembic import command
from alembic.config import Config
from app.models import User,UserSession,AccountAudit
from app.services import accounts
from app.database.postgresql import require_postgresql_schema

PASSWORD='synthetic-pg-password'


def setup(factory):
    with factory() as db:
        first=legacy_user(db,'admin-a','Admin A',PASSWORD,'admin')
        second=legacy_user(db,'admin-b','Admin B',PASSWORD,'admin',actor_id=first)
    return first,second


@pytest.mark.parametrize('pg_factory',['0005_assignment_history'],indirect=True)
def test_migration_preserves_users_credentials_and_does_not_invent_master_or_audit(pg_factory):
    engine=pg_factory.kw['bind'];encoded=accounts.password_hash(PASSWORD)
    with engine.begin() as db:
        key=db.scalar(text("INSERT INTO users(username,display_name,password_hash,role,is_active,failed_attempts,created_at,updated_at,revision) VALUES ('admin','master',:encoded,'admin',true,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1) RETURNING id"),{'encoded':encoded})
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with engine.begin() as db:
        cfg.attributes['connection']=db;command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    require_postgresql_schema(engine)
    with pg_factory() as db:
        user=db.get(User,key)
        assert (user.username,user.display_name,user.password_hash,user.role)==('admin','master',encoded,'admin')
        assert db.scalar(select(func.count()).select_from(AccountAudit).where(AccountAudit.operation.in_(('create','edit','role_change','block','unblock','password_reset','password_change','sessions_revoke','promote_master'))))==0
        accounts.promote_master(db,key,PASSWORD,confirmed=True)
        assert user.id==key and user.password_hash==encoded and user.role=='master'
        assert db.scalar(select(func.count()).select_from(AccountAudit).where(AccountAudit.operation.in_(('create','edit','role_change','block','unblock','password_reset','password_change','sessions_revoke','promote_master'))))==1


@pytest.mark.parametrize('action',['block','demote'])
def test_concurrent_admin_operations_preserve_one_active_admin(pg_factory,action):
    a,b=setup(pg_factory);barrier=Barrier(2)
    with pg_factory() as db:
        master=legacy_user(db,'master','Master',PASSWORD,'admin',actor_id=a)
        accounts.promote_master(db,master,PASSWORD,confirmed=True)
    def write(key):
        with pg_factory() as db:
            rev=db.get(User,key).revision;barrier.wait(timeout=5)
            try:
                if action=='block':accounts.set_active(db,master,key,rev,False,confirmed=True)
                else:accounts.update_user(db,master,key,rev,role='user',confirmed=True)
                return 'ok'
            except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(write,[a,b]))==['ok','rejected']
    with pg_factory() as db:
        assert accounts.Repo.active_admins(db)==1
        assert db.scalar(select(func.count()).select_from(AccountAudit).where(AccountAudit.operation.in_(('create','edit','role_change','block','unblock','password_reset','password_change','sessions_revoke','promote_master'))))==5


@pytest.mark.parametrize('action',['is_active=false',"role='user'"])
def test_direct_sql_concurrent_updates_cannot_remove_all_admins(pg_factory,action):
    a,b=setup(pg_factory);barrier=Barrier(2);engine=pg_factory.kw['bind']
    def write(key):
        try:
            with engine.begin() as db:
                barrier.wait(timeout=5)
                db.execute(text(f'UPDATE users SET {action} WHERE id=:key'),{'key':key})
            return 'ok'
        except DBAPIError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(write,[a,b]))==['ok','rejected']
    with pg_factory() as db:assert accounts.Repo.active_admins(db)==1


def test_concurrent_promotions_only_one_master_and_one_promotion_audit(pg_factory):
    keys=setup(pg_factory);barrier=Barrier(2)
    def write(key):
        with pg_factory() as db:
            barrier.wait(timeout=5)
            try:accounts.promote_master(db,key,PASSWORD,confirmed=True);return 'ok'
            except ValueError:return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(write,keys))==['ok','rejected']
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(User).where(User.role=='master'))==1
        assert db.scalar(select(func.count()).select_from(AccountAudit).where(AccountAudit.operation.in_(('create','edit','role_change','block','unblock','password_reset','password_change','sessions_revoke','promote_master'))).where(AccountAudit.operation=='promote_master'))==1
        assert accounts.Repo.active_admins(db)==1


def test_postgresql_master_and_audit_guards_cannot_be_bypassed_with_sql(pg_factory):
    master,admin=setup(pg_factory);engine=pg_factory.kw['bind']
    with pg_factory() as db:accounts.promote_master(db,master,PASSWORD,confirmed=True)
    for sql in ["UPDATE users SET role='admin' WHERE id=:master","UPDATE users SET is_active=false WHERE id=:master",'DELETE FROM users WHERE id=:master',
                'UPDATE users SET id=999 WHERE id=:master',"UPDATE users SET username='renamed' WHERE id=:admin",'DELETE FROM account_audit',"UPDATE account_audit SET reason='changed'", "UPDATE users SET role='master' WHERE id=:admin",'UPDATE users SET is_active=false WHERE id=:admin']:
        with pytest.raises(DBAPIError),engine.begin() as db:db.execute(text(sql),{'master':master,'admin':admin})
    with pg_factory() as db:
        assert db.get(User,master).role=='master' and db.get(User,admin).is_active
        assert db.scalar(select(func.count()).select_from(AccountAudit).where(AccountAudit.operation.in_(('create','edit','role_change','block','unblock','password_reset','password_change','sessions_revoke','promote_master'))))==3


def test_postgresql_audit_failure_rolls_back_password_and_all_session_revocations(pg_factory):
    a,b=setup(pg_factory)
    with pg_factory() as db:
        accounts.promote_master(db,a,PASSWORD,confirmed=True)
        first,_=mfa_login(db,'admin-b',PASSWORD);second,_=mfa_login(db,'admin-b',PASSWORD)
        before=db.get(User,b).password_hash
        def fail(*args):raise RuntimeError('synthetic audit failure')
        event.listen(AccountAudit,'before_insert',fail)
        try:
            with pytest.raises(RuntimeError):accounts.reset_password(db,a,b,db.get(User,b).revision,'new-pg-test-password','new-pg-test-password',confirmed=True)
        finally:event.remove(AccountAudit,'before_insert',fail)
        assert db.get(User,b).password_hash==before
        assert all(accounts.authenticate(db,token)[0].id==b for token in (first,second))
        assert db.scalar(select(func.count()).select_from(AccountAudit).where(AccountAudit.operation.in_(('create','edit','role_change','block','unblock','password_reset','password_change','sessions_revoke','promote_master'))))==3


def test_postgresql_concurrent_revisions_and_actors_are_not_overwritten(pg_factory):
    a,b=setup(pg_factory)
    with pg_factory() as db:
        target=legacy_user(db,'target','Target',PASSWORD,'editor',actor_id=a);rev=db.get(User,target).revision
    barrier=Barrier(2)
    def write(actor):
        with pg_factory() as db:
            barrier.wait(timeout=5)
            try:accounts.update_user(db,actor,target,rev,display_name=f'Actor {actor}');return actor
            except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(write,[a,b]))
    assert results.count(None)==1;winner=next(value for value in results if value is not None)
    with pg_factory() as db:
        row=db.scalars(select(AccountAudit).where(AccountAudit.operation=='edit')).one()
        assert row.actor_user_id==winner and row.before['display_name']=='Target' and row.after['display_name']==f'Actor {winner}'


def test_schema_check_rejects_nonunique_master_index(pg_factory):
    engine=pg_factory.kw['bind']
    with engine.begin() as db:
        db.exec_driver_sql('DROP INDEX one_master')
        db.exec_driver_sql("CREATE INDEX one_master ON users(role) WHERE role='master'")
    with pytest.raises(ValueError,match='unique Master index'):require_postgresql_schema(engine)

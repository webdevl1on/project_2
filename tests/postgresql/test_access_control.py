"""Security 1.4 migration and concurrent ACL writes on isolated project2_ci schemas."""
from datetime import datetime,UTC,timedelta,date
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import text,select,func,event
from sqlalchemy.exc import DBAPIError
from alembic.config import Config
from alembic import command
from app.models import User,UserSession
from app.models.access import AccessRule,AccessAudit,AccessReview
from app.services import accounts,access,access_management as acl
from app.database.postgresql import require_postgresql_schema
from tests.mfa_helpers import login

PASSWORD='synthetic-strong-password'

@pytest.mark.parametrize('pg_factory',['0008_organization'],indirect=True)
def test_0009_preserves_identities_factors_sessions_and_grants_nothing(pg_factory):
    engine=pg_factory.kw['bind'];encoded=accounts.password_hash(PASSWORD)
    with engine.begin() as db:
        ids=[]
        for role in ['admin','editor','viewer']:
            key=db.scalar(text("INSERT INTO users(username,display_name,password_hash,role,is_active,failed_attempts,created_at,updated_at,revision) VALUES (:name,:name,:password,:role,true,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1) RETURNING id"),{'name':'legacy-'+role,'password':encoded,'role':role});ids.append(key)
        from app.models.mfa import TotpFactor
        from app.security.mfa_config import encrypt
        db.execute(TotpFactor.__table__.insert().values(user_id=ids[1],ciphertext=encrypt('JBSWY3DPEHPK3PXP'),last_step=-1))
        stamp=datetime.now(UTC).replace(tzinfo=None)
        for n,key in enumerate(ids):
            token=f'synthetic-session-{n}'
            db.execute(UserSession.__table__.insert().values(token_hash=accounts.digest_token(token),user_id=key,csrf_token='a'*64,public_id=str(n).zfill(32),created_at=stamp,last_activity=stamp,mfa_verified_at=stamp,expires_at=stamp+timedelta(hours=8)))
        db.execute(text("UPDATE users SET role='master' WHERE id=:id"),{'id':ids[0]})
        # A separate pre-existing Admin is kept; no role hierarchy changes guessed.
        db.execute(text("INSERT INTO users(username,display_name,password_hash,role,is_active,failed_attempts,created_at,updated_at,revision) VALUES ('retained-admin','Admin',:password,'admin',true,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"),{'password':encoded})
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with engine.begin() as db:cfg.attributes['connection']=db;command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    require_postgresql_schema(engine)
    with pg_factory() as db:
        assert [db.get(User,key).role for key in ids]==['master','user','user']
        assert all(db.get(User,key).password_hash==encoded and db.get(User,key).person_id is None for key in ids)
        assert db.scalar(select(func.count()).select_from(UserSession))==3
        assert db.scalar(select(func.count()).select_from(TotpFactor))==1
        assert db.scalar(select(func.count()).select_from(AccessRule))==0
        assert db.scalar(select(func.count()).select_from(AccessAudit))==2
        assert accounts.authenticate(db,'synthetic-session-1')[0].id==ids[1]
        assert not access.Access(db,ids[1]).allowed('medical')
        assert not access.Access(db,ids[0]).allowed('basic')

@pytest.fixture
def identities(pg_factory):
    with pg_factory() as db:
        admin=accounts.create_user(db,'pg-admin','Admin',PASSWORD,'admin')
        user=accounts.create_user(db,'pg-user','User',PASSWORD,'user',actor_id=admin)
        token,_=login(db,'pg-admin',PASSWORD)
    return pg_factory,admin,user,accounts.digest_token(token)


def bind(db,admin,token):db.info.update(access_actor=admin,access_session_hash=token)


def test_concurrent_matrix_revision_retains_one_success_and_full_audit(identities):
    factory,admin,user,token=identities
    with factory() as db:revision=db.get(User,user).revision
    barrier=Barrier(2)
    def write(index):
        with factory() as db:
            bind(db,admin,token);barrier.wait(timeout=5)
            try:
                acl.save_matrix(db,admin,user,[{'category':'basic','action':'read','scope_type':'global','effect':'ALLOW' if index else 'DENY'}],revision,'Паралельна перевірка')
                return True
            except ValueError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(write,[0,1]))==[False,True]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(AccessAudit).where(AccessAudit.operation=='matrix_change'))==1
        assert db.scalar(select(func.count()).select_from(AccessRule))==1


def test_acl_audit_failure_is_atomic_and_rows_cannot_be_deleted(identities):
    factory,admin,user,token=identities
    with factory() as db:
        bind(db,admin,token)
        def fail(*_):raise RuntimeError('synthetic audit failure')
        event.listen(AccessAudit,'before_insert',fail)
        try:
            with pytest.raises(RuntimeError):acl.save_rule(db,admin,user,{'category':'basic','action':'read','scope_type':'global'},db.get(User,user).revision,'Запис із відмовою аудиту')
        finally:event.remove(AccessAudit,'before_insert',fail)
        assert db.scalar(select(func.count()).select_from(AccessRule))==0
        key=acl.save_rule(db,admin,user,{'category':'basic','action':'read','scope_type':'global'},db.get(User,user).revision,'Підтверджений запис')
    for sql in ['DELETE FROM access_rules','DELETE FROM access_audit',"UPDATE access_audit SET reason='rewrite'"]:
        with pytest.raises(DBAPIError),factory.kw['bind'].begin() as db:db.execute(text(sql))


def test_database_rejects_old_roles_and_ambiguous_person_link(identities):
    factory,admin,user,token=identities;engine=factory.kw['bind']
    with factory() as db:
        from app.models import Person
        p=Person();db.add(p);db.commit();pid=p.person_id
        bind(db,admin,token);acl.link_person(db,admin,user,pid,db.get(User,user).revision,'Явний зв’язок')
    with pytest.raises(DBAPIError),engine.begin() as db:db.execute(text("UPDATE users SET role='editor' WHERE id=:id"),{'id':user})
    with pytest.raises(DBAPIError),engine.begin() as db:db.execute(text('UPDATE users SET person_id=:pid WHERE id=:id'),{'id':admin,'pid':pid})

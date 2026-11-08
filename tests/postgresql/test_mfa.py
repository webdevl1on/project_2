"""Persistent MFA state and races on actual PostgreSQL 17, project2_ci only."""
from tests.access_helpers import legacy_user
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta,UTC
from pathlib import Path
import pytest,pyotp
from sqlalchemy import text,select,func
from alembic.config import Config
from alembic import command
from app.services import accounts,mfa
from app.models import User,UserSession,AuthFlow,TotpFactor,RecoveryCode,AccountAudit
from app.security.mfa_config import require_keys,MARKER,encrypt
from app.models.mfa import MfaKeyState
from app.database.postgresql import require_postgresql_schema
from tests.test_mfa import enroll,PASSWORD

@pytest.mark.parametrize('pg_factory',['0006_account_management'],indirect=True)
def test_additive_migration_keeps_master_and_invalidates_old_password_sessions(pg_factory):
    engine=pg_factory.kw['bind']
    with pg_factory() as db:
        # Frozen 0006 schema has no User.person_id; seed without the new ORM.
        encoded=accounts.password_hash(PASSWORD)
        uid=db.scalar(text("INSERT INTO users(username,display_name,password_hash,role,is_active,failed_attempts,created_at,updated_at,revision) VALUES ('mfa-admin','Master',:password,'admin',true,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1) RETURNING id"),{'password':encoded})
        db.execute(text("UPDATE users SET role='master' WHERE id=:uid"),{'uid':uid})
        db.execute(text("INSERT INTO user_sessions(token_hash,user_id,csrf_token,expires_at) VALUES (:token,:uid,'old-csrf',CURRENT_TIMESTAMP+interval '8 hours')"),{'token':accounts.digest_token('old-token'),'uid':uid});db.commit()
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with engine.begin() as db:cfg.attributes['connection']=db;command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    require_postgresql_schema(engine)
    with pg_factory() as db:
        db.add(MfaKeyState(id=1,ciphertext=encrypt(MARKER)));db.commit()
        user=db.get(User,uid);assert user.role=='master' and user.password_hash==encoded
        with pytest.raises(PermissionError):accounts.authenticate(db,'old-token')
        token,_,_=enroll(db,uid);result=mfa.finish(db,token);assert accounts.authenticate(db,result['token'])[0].id==uid

@pytest.mark.parametrize('operation',['backup','totp','finish'])
def test_concurrent_single_use_factor_or_flow(pg_factory,monkeypatch,operation):
    clock=[mfa.now()];monkeypatch.setattr(mfa,'now',lambda:clock[0])
    with pg_factory() as db:
        uid=legacy_user(db,'mfa-admin','Admin',PASSWORD,'admin');token,setup,codes=enroll(db,uid);mfa.finish(db,token)
        token,_=accounts.login(db,'mfa-admin',PASSWORD)
        if operation=='finish':mfa.prove(db,token,'backup',codes[0])
        other,_=accounts.login(db,'mfa-admin',PASSWORD)
    clock[0]+=timedelta(seconds=30);barrier=Barrier(2)
    def attempt(index):
        with pg_factory() as db:
            barrier.wait(timeout=5)
            try:
                if operation=='finish':mfa.finish(db,token)
                elif operation=='backup':mfa.prove(db,token if index==0 else other,'backup',codes[0])
                else:mfa.prove(db,token if index==0 else other,'totp',pyotp.TOTP(setup['secret']).at(clock[0].replace(tzinfo=UTC)))
                return True
            except PermissionError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(attempt,[0,1]))==[False,True]


def test_multiple_sessions_process_restart_and_rotation(pg_factory,monkeypatch):
    from app.services import mfa_keys
    import app.database.db as database
    engine=pg_factory.kw['bind']
    with pg_factory() as db:
        uid=legacy_user(db,'mfa-admin','Admin',PASSWORD,'admin');token,setup,codes=enroll(db,uid);session=mfa.finish(db,token)
        pending,_=accounts.login(db,'mfa-admin',PASSWORD)
    # A completely new Session consumes state persisted by the previous worker.
    with pg_factory() as db:mfa.prove(db,pending,'backup',codes[0]);assert mfa.finish(db,pending)['token']
    monkeypatch.setenv('PROJECT2_MFA_KEYS','{"test":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=","next":"AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="}')
    monkeypatch.setenv('PROJECT2_MFA_CURRENT_KEY','next');monkeypatch.setattr(database,'engine',engine);monkeypatch.setattr('sys.argv',['mfa_keys','--rotate'])
    mfa_keys.main()
    monkeypatch.setenv('PROJECT2_MFA_KEYS','{"next":"AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="}')
    with pg_factory() as db:
        require_keys(db);assert db.scalar(select(TotpFactor)).ciphertext.startswith('next:')
        assert accounts.authenticate(db,session['token'])


def test_pending_flow_survives_two_separate_server_processes(pg_factory):
    import os,sys,json,subprocess
    with pg_factory() as db:
        uid=legacy_user(db,'mfa-admin','Admin',PASSWORD,'admin');token,_,codes=enroll(db,uid);mfa.finish(db,token)
        pending,_=accounts.login(db,'mfa-admin',PASSWORD)
        schema=db.scalar(text('SELECT current_schema()'))
    script='''
import sys,json
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.services import mfa
payload=json.load(sys.stdin)
url=make_url(payload['url'])
assert url.database=='project2_ci' and payload['schema'].startswith('project2_test_')
engine=create_engine(url,connect_args={'options':'-c search_path='+payload['schema']+',public -c timezone=UTC'})
with Session(engine) as db:
    if payload['action']=='prove':mfa.prove(db,payload['token'],'backup',payload['code'])
    else:mfa.finish(db,payload['token'])
engine.dispose()
print('ok')
'''
    for action in ['prove','finish']:
        payload={'url':os.environ['PROJECT2_TEST_DATABASE_URL'],'schema':schema,'token':pending,'code':codes[0],'action':action}
        result=subprocess.run([sys.executable,'-c',script],input=json.dumps(payload),capture_output=True,text=True,timeout=30)
        assert result.returncode==0,result.stderr
        assert result.stdout.strip()=='ok'
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(UserSession).where(UserSession.mfa_verified_at.is_not(None)))==2
        with pytest.raises(PermissionError):mfa.finish(db,pending)

"""Security 1.3 with managed time and actual WebAuthn signature validation."""
import base64,json,hashlib,secrets
from datetime import datetime,timedelta,UTC
import pytest,pyotp,cbor2
from sqlalchemy import create_engine,select,func,event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from app.models import User,UserSession,AccountAudit,AuthFlow,TotpFactor,Passkey,RecoveryCode
from app.database.base import Base
from app.database.db import get_db
from app.main import app
from app.services import accounts,mfa
from app.security.mfa_config import decrypt,require_keys

PASSWORD='synthetic-mfa-password'
def b64(v):return base64.urlsafe_b64encode(v).decode().rstrip('=')

@pytest.fixture
def prepared(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'mfa.sqlite3'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine)
    clock=[datetime(2026,11,7,12)]
    monkeypatch.setattr(mfa,'now',lambda:clock[0])
    with factory() as db:uid=accounts.create_user(db,'mfa-admin','Тестовий Admin',PASSWORD,'admin')
    def override():
        with factory() as db:yield db
    previous=dict(app.dependency_overrides);app.dependency_overrides[get_db]=override
    with TestClient(app,base_url='https://testserver') as client:yield client,factory,uid,clock
    app.dependency_overrides.clear();app.dependency_overrides.update(previous);engine.dispose()

def enroll(db,uid,name='mfa-admin'):
    token,_=accounts.login(db,name,PASSWORD);setup=mfa.totp_start(db,token)
    code=pyotp.TOTP(setup['secret']).at(mfa.now().replace(tzinfo=UTC));result=mfa.totp_confirm(db,token,code)
    return token,setup,result['codes']

def registration(options,origin='https://testserver',rp='testserver',uv=True):
    private=ec.generate_private_key(ec.SECP256R1());public=private.public_key().public_numbers();credential=secrets.token_bytes(32)
    cose=cbor2.dumps({1:2,3:-7,-1:1,-2:public.x.to_bytes(32,'big'),-3:public.y.to_bytes(32,'big')})
    auth=hashlib.sha256(rp.encode()).digest()+bytes([0x45 if uv else 0x41])+b'\0'*4+b'\0'*16+len(credential).to_bytes(2,'big')+credential+cose
    client=json.dumps({'type':'webauthn.create','challenge':options['challenge'],'origin':origin}).encode()
    return private,credential,{'id':b64(credential),'rawId':b64(credential),'type':'public-key','response':{'clientDataJSON':b64(client),'attestationObject':b64(cbor2.dumps({'fmt':'none','attStmt':{},'authData':auth}))}}

def assertion(options,private,credential,origin='https://testserver',rp='testserver',uv=True,challenge=None):
    auth=hashlib.sha256(rp.encode()).digest()+bytes([5 if uv else 1])+(1).to_bytes(4,'big')
    client=json.dumps({'type':'webauthn.get','challenge':challenge or options['challenge'],'origin':origin}).encode()
    signature=private.sign(auth+hashlib.sha256(client).digest(),ec.ECDSA(hashes.SHA256()))
    return {'id':b64(credential),'rawId':b64(credential),'type':'public-key','response':{'clientDataJSON':b64(client),'authenticatorData':b64(auth),'signature':b64(signature)}}

def test_password_only_pending_enrollment_and_legacy_session_denied(prepared):
    client,factory,uid,clock=prepared
    response=client.post('/auth/login',json={'username':'mfa-admin','password':PASSWORD});assert response.status_code==200
    assert 'project2_user' not in client.cookies and response.json()['redirect_to']=='/auth/mfa'
    assert client.get('/auth/mfa').status_code==200
    for path in ['/persons','/admin','/auth/me','/account/security','/persons/1/documents/files/1']:assert client.get(path).status_code==401
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(UserSession))==0
        db.add(UserSession(token_hash=accounts.digest_token('legacy'),user_id=uid,csrf_token='legacy',expires_at=clock[0]+timedelta(hours=8)));db.commit()
        with pytest.raises(PermissionError):accounts.authenticate(db,'legacy')

def test_totp_enrollment_encrypted_secret_codes_once_and_real_login(prepared):
    client,factory,uid,clock=prepared
    with factory() as db:
        token,setup,codes=enroll(db,uid);factor=db.scalar(select(TotpFactor));assert setup['secret'] not in factor.ciphertext and decrypt(factor.ciphertext)==setup['secret']
        assert len(codes)==10 and db.scalar(select(func.count()).select_from(RecoveryCode))==10
        with pytest.raises(PermissionError):accounts.authenticate(db,token)
        session=mfa.finish(db,token);assert accounts.authenticate(db,session['token'])[0].id==uid
        with pytest.raises(PermissionError):mfa.finish(db,token)
        pending,_=accounts.login(db,'mfa-admin',PASSWORD)
        with pytest.raises(PermissionError):mfa.prove(db,pending,'totp',pyotp.TOTP(setup['secret']).at(clock[0].replace(tzinfo=UTC)))
        clock[0]+=timedelta(seconds=30)
        mfa.prove(db,pending,'totp',pyotp.TOTP(setup['secret']).at(clock[0].replace(tzinfo=UTC)));assert mfa.finish(db,pending)['token']
        payload=json.dumps([r.after for r in db.scalars(select(AccountAudit))]);assert setup['secret'] not in payload
        assert all(code not in payload for code in codes)

@pytest.mark.parametrize('role',['master','admin','editor','viewer'])
def test_all_roles_migrate_without_identity_changes(prepared,role):
    client,factory,uid,clock=prepared
    with factory() as db:
        if role=='master':accounts.promote_master(db,uid,PASSWORD,confirmed=True)
        elif role!='admin':uid=accounts.create_user(db,'other-'+role,'Інша роль',PASSWORD,role,actor_id=uid)
        user=db.get(User,uid);before=(user.id,user.role,user.password_hash)
        token,setup,codes=enroll(db,uid,user.username)
        assert mfa.finish(db,token)['token'] and (user.id,user.role,user.password_hash)==before

@pytest.mark.parametrize('condition',['expired','bad_code','exhausted','password_changed'])
def test_pending_rejection(prepared,condition):
    client,factory,uid,clock=prepared
    with factory() as db:
        token,setup,codes=enroll(db,uid);mfa.finish(db,token);pending,_=accounts.login(db,'mfa-admin',PASSWORD)
        if condition=='expired':clock[0]+=timedelta(minutes=6)
        elif condition=='password_changed':accounts.change_password(db,uid,PASSWORD,PASSWORD+'-new',PASSWORD+'-new')
        elif condition=='exhausted':
            for _ in range(5):
                with pytest.raises(PermissionError):mfa.prove(db,pending,'totp','wrong')
        with pytest.raises(PermissionError):mfa.prove(db,pending,'totp','000000' if condition!='bad_code' else 'wrong')

@pytest.mark.parametrize('bad',['challenge','origin','rp','uv','signature',None])
def test_real_webauthn_registration_and_signature_validation(prepared,bad):
    client,factory,uid,clock=prepared
    with factory() as db:
        token,_=accounts.login(db,'mfa-admin',PASSWORD);options=mfa.passkey_options(db,token,True)
        private,credential,registration_data=registration(options)
        assert len(mfa.passkey_verify(db,token,registration_data,True)['codes'])==10
        mfa.finish(db,token);token,_=accounts.login(db,'mfa-admin',PASSWORD);options=mfa.passkey_options(db,token)
        params={'origin':'https://evil.example'} if bad=='origin' else {'rp':'evil.example'} if bad=='rp' else {'uv':False} if bad=='uv' else {'challenge':'false-challenge'} if bad=='challenge' else {}
        response=assertion(options,private,credential,**params)
        if bad=='signature':response['response']['signature']=b64(b'bad')
        if bad is None:assert mfa.passkey_verify(db,token,response)['ok'];assert mfa.finish(db,token)['token']
        else:
            with pytest.raises(PermissionError):mfa.passkey_verify(db,token,response)
            # A failure consumes this challenge, even if the signature is subsequently fixed.
            with pytest.raises(PermissionError):mfa.passkey_verify(db,token,assertion(options,private,credential))

@pytest.mark.parametrize('bad',['origin','rp','uv'])
def test_registration_rejects_invalid_origin_rp_uv(prepared,bad):
    _,factory,_,_=prepared
    with factory() as db:
        token,_=accounts.login(db,'mfa-admin',PASSWORD);options=mfa.passkey_options(db,token,True)
        kwargs={'origin':'https://evil.example'} if bad=='origin' else {'rp':'evil.example'} if bad=='rp' else {'uv':False}
        _,_,response=registration(options,**kwargs)
        with pytest.raises(PermissionError):mfa.passkey_verify(db,token,response,True)
        assert db.scalar(select(func.count()).select_from(Passkey))==0

def test_recovery_codes_single_use_regenerate_and_reset(prepared):
    _,factory,uid,clock=prepared
    with factory() as db:
        token,_,codes=enroll(db,uid);session=mfa.finish(db,token)
        token,_=accounts.login(db,'mfa-admin',PASSWORD);mfa.prove(db,token,'backup',codes[0]);mfa.finish(db,token)
        token,_=accounts.login(db,'mfa-admin',PASSWORD)
        with pytest.raises(PermissionError):mfa.prove(db,token,'backup',codes[0])
        fresh=mfa.backup_generate(db,uid)
        with pytest.raises(PermissionError):mfa.prove(db,token,'backup',codes[1])
        mfa.prove(db,token,'backup',fresh[0]);mfa.finish(db,token)
        assert len(mfa.settings(db,uid)['passkeys'])==0

def test_idle_absolute_and_independent_sessions_with_managed_clock(prepared):
    _,factory,uid,clock=prepared
    with factory() as db:
        token,_,codes=enroll(db,uid);first=mfa.finish(db,token)
        clock[0]+=timedelta(minutes=10);token,_=accounts.login(db,'mfa-admin',PASSWORD);mfa.prove(db,token,'backup',codes[0]);second=mfa.finish(db,token)
        clock[0]+=timedelta(minutes=5)
        with pytest.raises(PermissionError):accounts.authenticate(db,first['token'])
        assert accounts.authenticate(db,second['token'])
        row=accounts.Repo.session(db,accounts.digest_token(second['token']));clock[0]=row.created_at+timedelta(hours=8);row.last_activity=clock[0];db.commit()
        with pytest.raises(PermissionError):accounts.authenticate(db,second['token'])

def test_http_full_flow_csrf_freshness_polling_and_own_sessions(prepared):
    client,factory,uid,clock=prepared
    first=client.post('/auth/login',json={'username':'mfa-admin','password':PASSWORD});csrf=first.json()['csrf_token'];headers={'X-CSRF-Token':csrf}
    assert client.post('/auth/mfa/totp/start',json={}).status_code==403
    setup=client.post('/auth/mfa/totp/start',json={},headers=headers).json()
    assert setup['qr'].startswith('data:image/png;')
    assert client.post('/auth/mfa/totp/confirm',json={'code':pyotp.TOTP(setup['secret']).at(clock[0].replace(tzinfo=UTC))},headers=headers).status_code==200
    done=client.post('/auth/mfa/finish',json={},headers=headers);assert done.status_code==200
    headers={'X-CSRF-Token':done.json()['csrf_token']}
    clock[0]+=timedelta(minutes=6)
    assert client.post('/account/security/backup',json={},headers=headers).status_code==403
    assert client.get('/account/sessions/data').json()['sessions'][0]['current']
    assert 'token_hash' not in client.get('/account/sessions/data').text
    for _ in range(10):assert client.get('/auth/me').status_code==200
    clock[0]+=timedelta(minutes=9)
    assert client.get('/auth/me').status_code==401
    assert client.post('/account/activity',headers=headers).status_code==401

def test_wrong_key_and_audit_failure_fail_closed(prepared,monkeypatch):
    _,factory,uid,_=prepared
    with factory() as db:
        token,_=accounts.login(db,'mfa-admin',PASSWORD);setup=mfa.totp_start(db,token)
        def fail(*args):raise RuntimeError('synthetic failure')
        event.listen(AccountAudit,'before_insert',fail)
        try:
            with pytest.raises(RuntimeError):mfa.totp_confirm(db,token,pyotp.TOTP(setup['secret']).at(mfa.now().replace(tzinfo=UTC)))
        finally:event.remove(AccountAudit,'before_insert',fail)
        assert db.scalar(select(TotpFactor)) is None
        monkeypatch.setenv('PROJECT2_MFA_KEYS','{"other":"AQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE="}');monkeypatch.setenv('PROJECT2_MFA_CURRENT_KEY','other')
        with pytest.raises(ValueError):require_keys(db)


def test_reauth_restores_freshness_without_extending_absolute_expiry(prepared):
    client,factory,uid,clock=prepared
    with factory() as db:token,_,codes=enroll(db,uid);session=mfa.finish(db,token)
    client.cookies.set('project2_user',session['token']);headers={'X-CSRF-Token':session['csrf_token']}
    absolute=session_deadline=None
    with factory() as db:absolute=accounts.Repo.session(db,accounts.digest_token(session['token'])).expires_at
    clock[0]+=timedelta(minutes=6)
    assert client.post('/account/security/backup',json={},headers=headers).status_code==403
    r=client.post('/account/security/reauth',json={'password':PASSWORD},headers=headers);assert r.status_code==200
    pending_headers={'X-CSRF-Token':client.get('/auth/mfa/state').json()['csrf_token']}
    assert client.post('/auth/mfa/prove',json={'method':'backup','code':codes[0]},headers=pending_headers).status_code==200
    assert client.post('/auth/mfa/finish',json={},headers=pending_headers).status_code==200
    assert client.post('/account/security/backup',json={},headers=headers).status_code==200
    with factory() as db:assert accounts.Repo.session(db,accounts.digest_token(session['token'])).expires_at==absolute


def test_admin_recovery_blocks_master_and_requires_reason_and_fresh_mfa(prepared):
    client,factory,uid,clock=prepared
    with factory() as db:
        accounts.promote_master(db,uid,PASSWORD,confirmed=True)
        admin=accounts.create_user(db,'other-admin','Admin',PASSWORD,'admin',actor_id=uid)
        token,_,codes=enroll(db,admin,'other-admin');session=mfa.finish(db,token)
    client.cookies.set('project2_user',session['token']);headers={'X-CSRF-Token':session['csrf_token']}
    body={'confirmed':True,'reason':'Перевірено синтетичну особу'}
    assert client.post(f'/admin/users/{uid}/reset-mfa',json=body,headers=headers).status_code==403
    with factory() as db:
        target=accounts.create_user(db,'target','Target',PASSWORD,'viewer',actor_id=uid)
        token,_,_=enroll(db,target,'target');old=mfa.finish(db,token)
    assert client.post(f'/admin/users/{target}/reset-mfa',json={'confirmed':True},headers=headers).status_code==409
    assert client.post(f'/admin/users/{target}/reset-mfa',json=body,headers=headers).status_code==200
    with factory() as db:
        with pytest.raises(PermissionError):accounts.authenticate(db,old['token'])
        token,_=accounts.login(db,'target',PASSWORD);assert mfa.state(db,token)['kind']=='setup'
        row=db.scalars(select(AccountAudit).where(AccountAudit.operation=='mfa_recover')).one();assert row.actor_user_id==admin and row.reason==body['reason']
    clock[0]+=timedelta(minutes=6)
    assert client.post(f'/admin/users/{target}/reset-mfa',json=body,headers=headers).status_code==403


def test_add_rename_revoke_passkey_and_last_factor_guard(prepared):
    _,factory,uid,clock=prepared
    with factory() as db:
        token,_,codes=enroll(db,uid);session=mfa.finish(db,token)
        with pytest.raises(ValueError):mfa.factor_change(db,uid,'totp')
        token,_=mfa.manage_start(db,uid,session['token']);opts=mfa.passkey_options(db,token,True);private,credential,response=registration(opts)
        mfa.passkey_verify(db,token,response,True);mfa.finish(db,token)
        key=db.scalar(select(Passkey));mfa.factor_change(db,uid,'passkey',key.id,'Новий ключ');assert db.get(Passkey,key.id).name=='Новий ключ'
        mfa.factor_change(db,uid,'passkey',key.id)
        with pytest.raises(PermissionError):accounts.authenticate(db,session['token'])
        token,_=accounts.login(db,'mfa-admin',PASSWORD)
        with pytest.raises(PermissionError):mfa.passkey_options(db,token)


def test_other_pending_setup_invalidated_after_first_enrollment(prepared):
    _,factory,uid,_=prepared
    with factory() as db:
        first,_=accounts.login(db,'mfa-admin',PASSWORD);second,_=accounts.login(db,'mfa-admin',PASSWORD)
        setup=mfa.totp_start(db,first);mfa.totp_confirm(db,first,pyotp.TOTP(setup['secret']).at(mfa.now().replace(tzinfo=UTC)))
        with pytest.raises(PermissionError):mfa.passkey_options(db,second,True)


def test_passkey_audit_failure_rolls_back_factor_and_flow(prepared):
    _,factory,uid,_=prepared
    with factory() as db:
        token,_=accounts.login(db,'mfa-admin',PASSWORD);opts=mfa.passkey_options(db,token,True);_,_,response=registration(opts)
        def fail(*args):raise ValueError('synthetic audit refusal')
        event.listen(AccountAudit,'before_insert',fail)
        try:
            with pytest.raises(ValueError,match='synthetic audit'):mfa.passkey_verify(db,token,response,True)
        finally:event.remove(AccountAudit,'before_insert',fail)
        assert db.scalar(select(Passkey)) is None and not mfa.pending(db,token)[1].verified


def test_own_sessions_cannot_revoke_other_user_or_current(prepared):
    client,factory,uid,clock=prepared
    with factory() as db:
        token,_,codes=enroll(db,uid);first=mfa.finish(db,token)
        token,_=accounts.login(db,'mfa-admin',PASSWORD);mfa.prove(db,token,'backup',codes[0]);other=mfa.finish(db,token)
        target=accounts.create_user(db,'second-user','Other',PASSWORD,'viewer',actor_id=uid)
        token,_,_=enroll(db,target,'second-user');foreign=mfa.finish(db,token)
        foreign_id=accounts.Repo.session(db,accounts.digest_token(foreign['token'])).public_id
    client.cookies.set('project2_user',first['token']);headers={'X-CSRF-Token':first['csrf_token']}
    assert len(client.get('/account/sessions/data').json()['sessions'])==2
    assert client.post('/account/sessions/revoke',json={'id':foreign_id},headers=headers).status_code==200
    assert client.post('/account/sessions/revoke',json={'all_others':True},headers=headers).status_code==200
    with factory() as db:
        assert accounts.authenticate(db,first['token']);assert accounts.authenticate(db,foreign['token'])
        with pytest.raises(PermissionError):accounts.authenticate(db,other['token'])


def test_local_master_recovery_preserves_identity_and_requires_password(prepared):
    _,factory,uid,clock=prepared
    with factory() as db:
        accounts.promote_master(db,uid,PASSWORD,confirmed=True);token,_,_=enroll(db,uid);session=mfa.finish(db,token);old=db.get(User,uid).password_hash
        with pytest.raises(PermissionError):mfa.recover(db,None,uid,'Перевірено власника',password='wrong')
        mfa.recover(db,None,uid,'Перевірено власника локальним адміністратором ОС',password=PASSWORD)
        assert db.get(User,uid).role=='master' and db.get(User,uid).password_hash==old
        with pytest.raises(PermissionError):accounts.authenticate(db,session['token'])
        token,_=accounts.login(db,'mfa-admin',PASSWORD);assert mfa.state(db,token)['kind']=='setup'
        audit=db.scalar(select(AccountAudit).where(AccountAudit.operation=='mfa_recover'));assert audit.actor_user_id is None


def test_recovery_cli_requires_os_administrator_before_opening_database(monkeypatch):
    import os
    from app.services import recover_master_mfa
    if os.name=='nt':pytest.skip('POSIX privilege guard; Windows Administrator check is platform-specific')
    monkeypatch.setattr('sys.argv',['recover_master_mfa','--user-id','1']);monkeypatch.setattr(os,'geteuid',lambda:1000)
    with pytest.raises(SystemExit):recover_master_mfa.main()


def test_forced_revocation_also_invalidates_verified_pending_login(prepared):
    _,factory,uid,_=prepared
    with factory() as db:
        token,_,codes=enroll(db,uid);mfa.finish(db,token)
        pending,_=accounts.login(db,'mfa-admin',PASSWORD);mfa.prove(db,pending,'backup',codes[0])
        accounts.revoke_all_sessions(db,uid,uid,db.get(User,uid).revision,confirmed=True)
        with pytest.raises(PermissionError):mfa.finish(db,pending)


def test_confirmed_totp_replacement_allows_recovery_without_passkey(prepared):
    _,factory,uid,clock=prepared
    with factory() as db:
        token,old,codes=enroll(db,uid);session=mfa.finish(db,token)
        token,_=mfa.manage_start(db,uid,session['token']);new=mfa.totp_start(db,token)
        result=mfa.totp_confirm(db,token,pyotp.TOTP(new['secret']).at(clock[0].replace(tzinfo=UTC)))
        assert result['redirect_to']=='/auth/login' and decrypt(db.scalar(select(TotpFactor)).ciphertext)==new['secret']
        with pytest.raises(PermissionError):accounts.authenticate(db,session['token'])
        pending,_=accounts.login(db,'mfa-admin',PASSWORD);clock[0]+=timedelta(seconds=30)
        mfa.prove(db,pending,'totp',pyotp.TOTP(new['secret']).at(clock[0].replace(tzinfo=UTC)));assert mfa.finish(db,pending)['token']


def test_factor_management_flow_does_not_extend_fresh_mfa_window(prepared):
    _,factory,uid,clock=prepared
    with factory() as db:
        token,_,_=enroll(db,uid);session=mfa.finish(db,token)
        clock[0]+=timedelta(minutes=4);manage,_=mfa.manage_start(db,uid,session['token'])
        clock[0]+=timedelta(minutes=2)
        with pytest.raises(PermissionError):mfa.totp_start(db,manage)

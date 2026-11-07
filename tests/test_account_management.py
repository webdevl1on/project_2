from tests.mfa_helpers import finish_http
from tests.mfa_helpers import login as mfa_login
"""Security 1.2 on synthetic identities and isolated SQLite databases."""
from datetime import datetime,UTC,timedelta
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,func,event,text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from app.database.base import Base
from app.database.db import get_db
from app.main import app
from app.models import User,UserSession,AccountAudit
from app.services import accounts,account_management as view

PASSWORD='synthetic-initial-password'
NEW='synthetic-replacement-password'

@pytest.fixture
def identities(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'accounts.sqlite3'),connect_args={'check_same_thread':False})
    @event.listens_for(engine,'connect')
    def foreign_keys(connection,record):connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine);factory=sessionmaker(engine)
    with factory() as db:
        admin=accounts.create_user(db,'admin','master',PASSWORD,'admin')
        editor=accounts.create_user(db,'editor','Редактор',PASSWORD,'editor',actor_id=admin)
        viewer=accounts.create_user(db,'viewer','Спостерігач',PASSWORD,'viewer',actor_id=admin)
    yield factory,{'admin':admin,'editor':editor,'viewer':viewer}
    engine.dispose()

@pytest.fixture
def web(identities):
    factory,ids=identities
    def override():
        with factory() as db:yield db
    previous=dict(app.dependency_overrides);app.dependency_overrides[get_db]=override
    with TestClient(app,base_url='https://testserver') as client:yield client,factory,ids
    app.dependency_overrides.clear();app.dependency_overrides.update(previous)


def login(client,name='admin',password=PASSWORD):
    response=finish_http(client,client.post('/auth/login',json={'username':name,'password':password}))
    assert response.status_code==200,response.text
    return {'X-CSRF-Token':response.json()['csrf_token']}


def revision(db,key):return db.get(User,key,populate_existing=True).revision


def promote(factory,ids):
    with factory() as db:accounts.promote_master(db,ids['admin'],PASSWORD,confirmed=True)


def test_explicit_promotion_preserves_identity_password_and_history(identities):
    factory,ids=identities
    with factory() as db:
        user=db.get(User,ids['admin']);original=(user.id,user.username,user.display_name,user.password_hash,user.created_at)
        assert user.role=='admin' and view.listing(db,user.id)['needs_admin'] is False
        for args in ({'confirmed':False},{'confirmed':True,'expected_revision':999}):
            with pytest.raises(ValueError):accounts.promote_master(db,user.id,PASSWORD,**args)
        with pytest.raises(ValueError,match='пароль'):accounts.promote_master(db,user.id,'wrong-password',confirmed=True)
        accounts.promote_master(db,user.id,PASSWORD,confirmed=True)
        assert (user.id,user.username,user.display_name,user.password_hash,user.created_at)==original
        assert user.role=='master' and view.listing(db,user.id)['needs_admin']
        with pytest.raises(ValueError):accounts.promote_master(db,user.id,PASSWORD,confirmed=True)
        assert accounts.authorize(db,user.id,('admin',)).id==user.id
        other=accounts.create_user(db,'other-admin','Admin',PASSWORD,'admin',actor_id=user.id)
        assert not view.listing(db,user.id)['needs_admin']
        with pytest.raises(ValueError,match='уже існує'):accounts.promote_master(db,other,PASSWORD,confirmed=True)
        row=db.scalars(select(AccountAudit).where(AccountAudit.operation=='promote_master')).one()
        assert row.actor_user_id==user.id and row.before['role']=='admin' and row.after['role']=='master'


@pytest.mark.parametrize('kind',['viewer','editor','disabled','technical','missing'])
def test_promotion_only_existing_active_personal_admin(identities,kind):
    factory,ids=identities
    with factory() as db:
        key=ids.get(kind,999)
        if kind=='disabled':
            key=accounts.create_user(db,'disabled','Вимкнений',PASSWORD,'admin',actor_id=ids['admin'])
            accounts.set_active(db,ids['admin'],key,revision(db,key),False,confirmed=True)
        if kind=='technical':
            user=User(username='legacy',display_name='Технічний',password_hash='open-access-only$test',role='admin');db.add(user);db.commit();key=user.id
        with pytest.raises(ValueError):accounts.promote_master(db,key,PASSWORD,confirmed=True)
        assert not db.scalar(select(User.id).where(User.role=='master'))


@pytest.mark.parametrize('action',['edit','role','block','reset','revoke'])
def test_admin_cannot_change_master(identities,action):
    factory,ids=identities;promote(factory,ids)
    with factory() as db:
        actor=accounts.create_user(db,'another-admin','Admin',PASSWORD,'admin',actor_id=ids['admin']);key=ids['admin'];rev=revision(db,key)
        operations={'edit':lambda:accounts.update_user(db,actor,key,rev,display_name='Changed'),
                    'role':lambda:accounts.update_user(db,actor,key,rev,role='editor',confirmed=True),
                    'block':lambda:accounts.set_active(db,actor,key,rev,False,confirmed=True),
                    'reset':lambda:accounts.reset_password(db,actor,key,rev,NEW,NEW,confirmed=True),
                    'revoke':lambda:accounts.revoke_all_sessions(db,actor,key,rev,confirmed=True)}
        with pytest.raises(PermissionError,match='Master'):operations[action]()
        assert db.get(User,key).display_name=='master' and db.get(User,key).is_active


@pytest.mark.parametrize('action',['block','demote'])
def test_last_admin_excludes_master_and_technical_accounts(identities,action):
    factory,ids=identities;promote(factory,ids)
    with factory() as db:
        key=accounts.create_user(db,'only-admin','Admin',PASSWORD,'admin',actor_id=ids['admin'])
        db.add(User(username='legacy',display_name='Legacy',password_hash='dev-only$test',role='admin'));db.commit()
        with pytest.raises(ValueError,match='останнього'):
            if action=='block':accounts.set_active(db,ids['admin'],key,revision(db,key),False,confirmed=True)
            else:accounts.update_user(db,ids['admin'],key,revision(db,key),role='editor',confirmed=True)
        # Direct ORM writes are guarded too.
        user=db.get(User,key)
        with pytest.raises(IntegrityError):
            if action=='block':user.is_active=False
            else:user.role='editor'
            db.commit()
        db.rollback();assert db.get(User,key).role=='admin' and db.get(User,key).is_active


@pytest.mark.parametrize('action',['demote','block','delete','id','username','audit_update','audit_delete','insert_master'])
def test_database_guards_protect_master_and_append_only_audit(identities,action):
    factory,ids=identities;promote(factory,ids)
    with factory() as db:
        user=db.get(User,ids['admin']);audit=db.scalar(select(AccountAudit))
        with pytest.raises(IntegrityError):
            if action=='demote':user.role='admin'
            elif action=='block':user.is_active=False
            elif action=='delete':db.delete(user)
            elif action=='id':user.id=99
            elif action=='username':user.username='changed'
            elif action=='audit_update':audit.reason='changed'
            elif action=='audit_delete':db.delete(audit)
            else:db.add(User(username='second-master',display_name='No',role='master',password_hash=accounts.password_hash(PASSWORD)))
            db.commit()
        db.rollback();assert db.get(User,ids['admin']).role=='master'


@pytest.mark.parametrize('operation',['block','reset','revoke','self_password'])
def test_all_sessions_revoked_and_passwords_never_audited(identities,operation):
    factory,ids=identities
    with factory() as db:
        key=ids['editor'];first,_=mfa_login(db,'editor',PASSWORD);second,_=mfa_login(db,'editor',PASSWORD)
        user=db.get(User,key);user.failed_attempts=3;user.locked_until=datetime.now(UTC)+timedelta(minutes=3);db.commit()
        locked=user.locked_until;rev=revision(db,key)
        if operation=='block':accounts.set_active(db,ids['admin'],key,rev,False,confirmed=True)
        elif operation=='reset':accounts.reset_password(db,ids['admin'],key,rev,NEW,NEW,confirmed=True)
        elif operation=='revoke':accounts.revoke_all_sessions(db,ids['admin'],key,rev,confirmed=True)
        else:accounts.change_password(db,key,PASSWORD,NEW,NEW)
        for token in (first,second):
            with pytest.raises(PermissionError):accounts.authenticate(db,token)
        user=db.get(User,key);assert user.role=='editor' and user.failed_attempts==3 and user.locked_until==locked
        if operation=='block':
            accounts.set_active(db,ids['admin'],key,revision(db,key),True,confirmed=True)
            assert db.get(User,key).locked_until==locked
            with pytest.raises(PermissionError):accounts.authenticate(db,first)
        if operation in ('reset','self_password'):assert accounts.verify_password(NEW,user.password_hash)
        snapshots=json.dumps([{'before':r.before,'after':r.after,'reason':r.reason} for r in db.scalars(select(AccountAudit))])
        for secret in (PASSWORD,NEW,first,second,user.password_hash,'csrf_token','password_hash'):assert secret not in snapshots


@pytest.mark.parametrize('current,password,confirmation',[
 ('incorrect',NEW,NEW),(PASSWORD,PASSWORD,PASSWORD),(PASSWORD,NEW,'different'),(PASSWORD,'short','short'),(PASSWORD,'x'*129,'x'*129)])
def test_own_password_rejections_are_atomic(identities,current,password,confirmation):
    factory,ids=identities
    with factory() as db:
        token,_=mfa_login(db,'viewer',PASSWORD)
        count=db.scalar(select(func.count()).select_from(AccountAudit))
        with pytest.raises(ValueError):accounts.change_password(db,ids['viewer'],current,password,confirmation)
        assert accounts.authenticate(db,token)[0].id==ids['viewer']
        assert db.scalar(select(func.count()).select_from(AccountAudit))==count


@pytest.mark.parametrize('operation',['create','edit','block','password','reset','revoke','promotion'])
def test_audit_failure_rolls_back_identity_and_sessions(identities,operation):
    factory,ids=identities
    with factory() as db:
        key=ids['editor'];token,_=mfa_login(db,'editor',PASSWORD);old=db.get(User,key).password_hash
        count=db.scalar(select(func.count()).select_from(AccountAudit))
        def fail(mapper,connection,target):raise RuntimeError('synthetic audit write failure')
        event.listen(AccountAudit,'before_insert',fail)
        try:
            with pytest.raises(RuntimeError,match='audit write'):
                if operation=='create':accounts.create_user(db,'rolled-back','No',PASSWORD,'admin',actor_id=ids['admin'])
                elif operation=='edit':accounts.update_user(db,ids['admin'],key,revision(db,key),display_name='No')
                elif operation=='block':accounts.set_active(db,ids['admin'],key,revision(db,key),False,confirmed=True)
                elif operation=='password':accounts.change_password(db,key,PASSWORD,NEW,NEW)
                elif operation=='reset':accounts.reset_password(db,ids['admin'],key,revision(db,key),NEW,NEW,confirmed=True)
                elif operation=='promotion':accounts.promote_master(db,ids['admin'],PASSWORD,confirmed=True)
                else:accounts.revoke_all_sessions(db,ids['admin'],key,revision(db,key),confirmed=True)
        finally:event.remove(AccountAudit,'before_insert',fail)
        assert accounts.authenticate(db,token)[0].id==key
        assert db.get(User,key).password_hash==old and db.get(User,key).display_name=='Редактор'
        assert db.get(User,ids['admin']).role=='admin'
        assert not db.scalar(select(User).where(User.username=='rolled-back'))
        assert db.scalar(select(func.count()).select_from(AccountAudit))==count


def test_revision_confirmations_and_two_audit_authors(identities):
    factory,ids=identities
    with factory() as db:
        other=accounts.create_user(db,'other-admin','Другий Admin',PASSWORD,'admin',actor_id=ids['admin']);key=ids['editor'];rev=revision(db,key)
        with pytest.raises(ValueError,match='Підтвердьте'):accounts.update_user(db,ids['admin'],key,rev,role='viewer')
        accounts.update_user(db,ids['admin'],key,rev,display_name='Перша зміна')
        with pytest.raises(ValueError,match='змінився'):accounts.update_user(db,other,key,rev,display_name='Застаріла')
        accounts.update_user(db,other,key,revision(db,key),role='viewer',confirmed=True)
        rows=list(db.scalars(select(AccountAudit).where(AccountAudit.user_id==key).order_by(AccountAudit.id)))
        assert [r.actor_user_id for r in rows[-2:]]==[ids['admin'],other]
        assert rows[-2].before['display_name']=='Редактор' and rows[-2].after['display_name']=='Перша зміна'
        assert rows[-1].before['role']=='editor' and rows[-1].after['role']=='viewer'


def test_web_admin_crud_csrf_actor_spoofing_and_safe_responses(web):
    client,factory,ids=web;headers=login(client)
    for path in ('/admin/users','/admin/users/new','/admin/users/audit',f'/admin/users/{ids["admin"]}'):
        assert client.get(path).status_code==200
    payload={'username':'new-admin','display_name':'Новий','password':NEW,'confirm_password':NEW,'role':'admin','actor_id':ids['viewer']}
    assert client.post('/admin/users/new',json=payload).status_code==403
    assert client.post('/admin/users/new',json=payload,headers={**headers,'Origin':'https://evil.example'}).status_code==403
    response=client.post('/admin/users/new',json=payload,headers=headers);assert response.status_code==200,response.text
    key=int(response.json()['redirect_to'].rsplit('/',1)[1])
    with factory() as db:
        assert db.scalar(select(AccountAudit).where(AccountAudit.user_id==key)).actor_user_id==ids['admin']
        rev=revision(db,key)
    assert client.post(f'/admin/users/{key}',json={'revision':rev,'display_name':'Виправлено','username':'ignored','actor_user_id':ids['viewer']},headers=headers).status_code==200
    listing=client.get('/admin/users',headers={'Accept':'application/json'});assert listing.status_code==200
    detail=client.get(f'/admin/users/{key}',headers={'Accept':'application/json'})
    for response in (listing,detail,client.get('/admin/users/audit',headers={'Accept':'application/json'})):
        for secret in (PASSWORD,NEW,'password_hash','csrf_token','token_hash'):assert secret not in response.text
    assert detail.json()['account']['username']=='new-admin'
    assert client.post('/auth/users',json={**payload,'username':'bad-master','role':'master'},headers=headers).status_code==400
    client.cookies.clear();login(client,'viewer')
    assert client.get('/admin/users').status_code==403
    assert client.get('/account/password').status_code==200


def test_role_effective_on_next_request_and_viewer_own_password(web):
    client,factory,ids=web;headers=login(client,'editor')
    with factory() as db:accounts.update_user(db,ids['admin'],ids['editor'],revision(db,ids['editor']),role='viewer',confirmed=True)
    assert client.post('/persons/1/personal-number',json={},headers=headers).status_code==403
    assert client.get('/persons').status_code==200
    response=client.post('/auth/password',json={'current_password':PASSWORD,'password':NEW,'confirm_password':NEW,'actor_user_id':ids['admin']},headers=headers)
    assert response.status_code==200,response.text
    assert client.get('/auth/me').status_code==401
    login(client,'editor',NEW)
    with factory() as db:
        row=db.scalars(select(AccountAudit).where(AccountAudit.operation=='password_change')).one()
        assert row.actor_user_id==ids['editor']


def test_master_existing_admin_routes_and_self_password(web):
    client,factory,ids=web;promote(factory,ids);headers=login(client)
    for path in ('/admin','/admin/staff','/admin/dictionaries','/admin/tcc','/admin/users','/admin/users/new'):
        assert client.get(path).status_code==200,path
    assert client.post('/auth/users',json={'username':'admin-created','display_name':'Admin','password':NEW,'role':'admin'},headers=headers).status_code==200
    response=client.post('/auth/password',json={'current_password':PASSWORD,'password':NEW,'confirm_password':NEW},headers=headers)
    assert response.status_code==200,response.text
    login(client,'admin',NEW)
    assert client.get('/auth/me').json()['role']=='master'


def test_temporary_lock_distinct_from_administrative_block(identities):
    factory,ids=identities
    with factory() as db:
        for _ in range(5):
            with pytest.raises(PermissionError):mfa_login(db,'editor','incorrect')
        rows={u['id']:u for u in view.listing(db,ids['admin'])['users']}
        assert rows[ids['editor']]['temporary_locked'] and rows[ids['editor']]['is_active']
        assert 'Тимчасово' in rows[ids['editor']]['status']
        accounts.set_active(db,ids['admin'],ids['viewer'],revision(db,ids['viewer']),False,confirmed=True)
        assert 'Вимкнений' in view.detail(db,ids['admin'],ids['viewer'])['account']['status']


def test_cli_requires_id_password_and_exact_confirmation(identities,monkeypatch,capsys):
    from app.services import promote_master as cli
    factory,ids=identities;engine=factory.kw['bind']
    class Settings:
        url='unused'
        def engine_options(self):return {}
        @staticmethod
        def read():return Settings()
    monkeypatch.setattr(cli,'Settings',Settings);monkeypatch.setattr(cli,'create_engine',lambda *a,**kw:engine)
    monkeypatch.setattr(cli,'require_current_schema',lambda value:None)
    with pytest.raises(SystemExit):cli.main([])
    monkeypatch.setattr(cli,'getpass',lambda prompt:PASSWORD)
    monkeypatch.setattr('builtins.input',lambda prompt:'MASTER 999')
    with pytest.raises(SystemExit):cli.main(['--user-id',str(ids['admin'])])
    with factory() as db:assert db.get(User,ids['admin']).role=='admin'
    monkeypatch.setattr('builtins.input',lambda prompt:f'MASTER {ids["admin"]}')
    cli.main(['--user-id',str(ids['admin'])])
    output=capsys.readouterr().out
    assert 'ID='+str(ids['admin']) in output and PASSWORD not in output and 'scrypt$' not in output
    with factory() as db:assert db.get(User,ids['admin']).role=='master'


def test_session_count_ignores_expired_but_revoke_removes_every_session(identities):
    factory,ids=identities
    with factory() as db:
        first,_=mfa_login(db,'editor',PASSWORD);second,_=mfa_login(db,'editor',PASSWORD)
        expired=db.get(UserSession,accounts.digest_token(first));expired.created_at=datetime.now(UTC)-timedelta(days=2);expired.last_activity=expired.created_at;expired.mfa_verified_at=expired.created_at;expired.expires_at=datetime.now(UTC)-timedelta(days=1);db.commit()
        assert view.detail(db,ids['admin'],ids['editor'])['active_sessions']==1
        accounts.revoke_all_sessions(db,ids['admin'],ids['editor'],revision(db,ids['editor']),confirmed=True)
        assert db.scalar(select(func.count()).select_from(UserSession).where(UserSession.user_id==ids['editor']))==0
        row=db.scalars(select(AccountAudit).where(AccountAudit.operation=='sessions_revoke')).one()
        assert row.after['revoked_sessions']==2


def test_master_inherits_document_override_file_history_and_medical_writes(identities,tmp_path):
    from app.models import Person,PersonDocument,DocumentFile
    from app.services import documents,document_files,medical
    from app.services.document_storage import DocumentStorage
    factory,ids=identities;promote(factory,ids);master=ids['admin']
    with factory() as db:
        person=Person();db.add(person);documents.seed_types(db);db.commit();pid=person.person_id
        key=documents.save(db,master,pid,'other',{'number':'synthetic'})
        documents.override(db,master,pid,key,db.get(PersonDocument,key).revision,'FILLED','Перевірено Master')
        storage=DocumentStorage(tmp_path/'copies')
        import base64
        image=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+Xn1cAAAAASUVORK5CYII=')
        file_id=document_files.attach(db,master,pid,key,db.get(PersonDocument,key).revision,image,'synthetic.png','front',storage=storage)
        document_files.remove(db,master,pid,file_id,db.get(DocumentFile,file_id).revision,'Перевірка історії')
        assert document_files.download(db,master,pid,file_id,history=True,storage=storage)[1].is_file()
        result=medical.save(db,master,pid,'dna',{'collected_on':'2026-01-01','envelope_number':'synthetic','storage_unit':'Тестова частина'})
        assert result['id']

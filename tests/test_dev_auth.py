import pytest
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.database.base import Base
from app.database.db import get_db
from app.main import app
from app.models import User,Person
from app.services import dev_auth

@pytest.fixture
def setup(tmp_path,monkeypatch):
    path=tmp_path/'dev_auth_test.sqlite3'
    engine=create_engine('sqlite:///'+str(path),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine)
    monkeypatch.setenv('PROJECT2_DEV_AUTH_BYPASS','1');monkeypatch.setenv('PROJECT2_DEV_AUTH_DATABASE',str(path))
    with factory() as db:
        person=Person();db.add(person);db.commit();pid=person.person_id
    def override():
        with factory() as db:yield db
    previous=dict(app.dependency_overrides);app.dependency_overrides[get_db]=override
    yield factory,pid,path
    app.dependency_overrides.clear();app.dependency_overrides.update(previous);engine.dispose()


def test_no_http_creation_idempotent_explicit_actor(setup):
    factory,_,_=setup
    with TestClient(app,base_url='http://localhost',client=('127.0.0.1',1234)) as client:assert client.get('/auth/me').status_code==503
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(User))==0
        key=dev_auth.initialize(db);assert dev_auth.initialize(db)==key
        assert db.scalar(select(func.count()).select_from(User))==1


def test_local_api_csrf_audit_files_and_disable(setup,monkeypatch,tmp_path):
    factory,pid,_=setup;monkeypatch.setenv('PROJECT2_DOCUMENT_STORAGE',str(tmp_path/'files'))
    with factory() as db:actor=dev_auth.initialize(db)
    with TestClient(app,base_url='http://localhost',client=('127.0.0.1',1234)) as client:
        me=client.get('/auth/me').json();assert me['dev_auth_bypass'] and me['id']==actor
        headers={'X-CSRF-Token':me['csrf_token']};url=f'/persons/{pid}/medical'
        assert client.post(url+'/exams',json={'fields':{}}).status_code==403
        key=client.post(url+'/exams',json={'fields':{'basis':'ILLNESS'}},headers=headers).json()['id']
        record=client.get(url).json()['exams'][0]
        assert client.post(url+f'/exams/{key}',json={'revision':record['revision'],'fields':{'status':'PLANNED'}},headers=headers).status_code==200
        assert all(r['actor_id']==actor for r in client.get(url).json()['audit'])
        docs=f'/persons/{pid}/documents';doc=client.post(docs,json={'type':'other','details':{}},headers=headers).json()['id']
        revision=next(r['revision'] for r in client.get(docs).json()['documents'] if r['id']==doc)
        upload=client.post(docs+f'/{doc}/files',files={'file':('test.pdf',b'%PDF-1.7 test','application/pdf')},data={'revision':revision},headers=headers)
        assert upload.status_code==200
        assert client.get(docs+f'/files/{upload.json()["id"]}').status_code==200
        assert client.post(docs+f'/{doc}/files',files={'file':('bad.pdf',b'bad','application/pdf')},data={'revision':revision},headers=headers).status_code==409
        assert client.post('/auth/users',json={'username':'extra','display_name':'Тест','password':'test-password-123','role':'viewer'},headers=headers).status_code==403
        assert client.post('/auth/logout',headers=headers).status_code==200
        monkeypatch.setenv('PROJECT2_DEV_AUTH_BYPASS','0');monkeypatch.setenv('PROJECT2_AUTH_ALLOW_LOCAL_HTTP','1')
        assert client.get('/auth/me').status_code==401

@pytest.mark.parametrize('peer,host,headers',[
 ('192.168.1.2','localhost',{}),('127.0.0.1','192.168.1.3',{}),('127.0.0.1','example.org',{}),
 *[('127.0.0.1','localhost',{k:'proxy'}) for k in ('Forwarded','X-Forwarded-For','X-Real-IP','Via')],
 ('127.0.0.1','localhost',{'Origin':'https://evil.example'}),('127.0.0.1','localhost',{'Sec-Fetch-Site':'cross-site'}),
 ('127.0.0.1','localhost',{'Sec-Fetch-Site':'same-site'})])
def test_nonlocal_proxy_origin_denied(setup,peer,host,headers):
    factory,_,_=setup
    with factory() as db:dev_auth.initialize(db)
    with TestClient(app,base_url='https://'+host,client=(peer,1234)) as client:assert client.get('/auth/me',headers=headers).status_code in (401,403)

@pytest.mark.parametrize('host,peer',[('127.0.0.1','127.0.0.1'),('localhost','127.0.0.1'),('[::1]','::1')])
def test_loopback_variants(setup,host,peer):
    factory,_,_=setup
    with factory() as db:dev_auth.initialize(db)
    with TestClient(app,base_url='http://localhost',client=(peer,1234)) as client:assert client.get('/auth/me',headers={'Host':host}).status_code==200


def test_wrong_database_disabled_and_existing_user_unchanged(setup,monkeypatch,tmp_path):
    factory,_,path=setup
    with factory() as db:
        monkeypatch.setenv('PROJECT2_DEV_AUTH_BYPASS','0')
        with pytest.raises(ValueError):dev_auth.initialize(db)
        monkeypatch.setenv('PROJECT2_DEV_AUTH_BYPASS','1');dev_auth.initialize(db)
        other=tmp_path/'other_test.sqlite3';other.touch();monkeypatch.setenv('PROJECT2_DEV_AUTH_DATABASE',str(other))
        with pytest.raises(ValueError):dev_auth.identity(db)
        monkeypatch.setenv('PROJECT2_DEV_AUTH_DATABASE',str(path))
        user=db.scalar(select(User));user.is_active=False;db.commit()
        with pytest.raises(ValueError):dev_auth.initialize(db)
        assert not db.get(User,user.id).is_active
        with pytest.raises(ValueError):dev_auth.database_path('data/database/project2.db')

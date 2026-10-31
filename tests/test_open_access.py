"""Unrestricted mode is the default; the retained protection is opt-in."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.database.db import get_db
from app.models import User,Person,PersonDocument
from app.services import documents
from tests.test_name_cases import factory,workbook,dictionary_data

@pytest.fixture
def opened(factory,monkeypatch,tmp_path):
    monkeypatch.delenv('PROJECT2_AUTH_ENABLED',raising=False)
    monkeypatch.delenv('PROJECT2_DEV_AUTH_BYPASS',raising=False)
    monkeypatch.delenv('PROJECT2_ADMIN_TOKEN',raising=False)
    monkeypatch.setenv('PROJECT2_DOCUMENT_STORAGE',str(tmp_path/'copies'))
    with factory() as db:
        p=Person();db.add(p);db.commit();pid=p.person_id
    def override():
        with factory() as db:yield db
    old=dict(app.dependency_overrides);app.dependency_overrides[get_db]=override
    with TestClient(app,base_url='http://192.168.1.50',client=('192.168.1.60',1234)) as client:
        yield client,pid,factory
    app.dependency_overrides.clear();app.dependency_overrides.update(old)


def test_default_open_without_token_password_or_localhost_and_idempotent_actor(opened):
    client,pid,factory=opened
    with factory() as db:assert db.scalar(select(func.count()).select_from(User))==0
    for _ in range(3):
        me=client.get('/auth/me',headers={'X-Forwarded-For':'192.168.1.70'}).json()
        assert me['open_access'] and me['role']=='admin' and me['csrf_token']==''
    with factory() as db:assert db.scalar(select(func.count()).select_from(User))==1
    assert client.post('/auth/login').json()['open_access']
    assert client.post('/auth/logout').status_code==200


def test_medical_crud_document_files_override_and_real_audit(opened):
    client,pid,factory=opened;url=f'/persons/{pid}/medical'
    me=client.get('/auth/me').json()
    injury=client.post(url+'/injuries',json={'fields':{'description':'Тестове поранення'}})
    assert injury.status_code==200
    data=client.get(url).json();assert len(data['tasks'])==2
    row=data['injuries'][0]
    assert client.post(url+f'/injuries/{row["id"]}',json={'fields':{'area':'Тестовий район'},'revision':row['revision']}).status_code==200
    assert all(e['actor_id']==me['id'] for e in client.get(url).json()['audit'])
    docs=f'/persons/{pid}/documents'
    key=client.post(docs,json={'type':'other','details':{'number':'001'}}).json()['id']
    row=next(r for r in client.get(docs).json()['documents'] if r['id']==key)
    assert client.post(docs+f'/{key}/override',json={'revision':row['revision'],'status':'NOT_FILLED','reason':'Тестова перевірка'}).status_code==200
    row=next(r for r in client.get(docs).json()['documents'] if r['id']==key)
    upload=client.post(docs+f'/{key}/files',files={'file':('copy.pdf',b'%PDF-1.7 synthetic','application/pdf')},data={'revision':row['revision']})
    assert upload.status_code==200
    assert client.get(docs+f'/files/{upload.json()["id"]}').status_code==200
    assert client.post(docs+f'/{key}/files',files={'file':('bad.pdf',b'bad','application/pdf')},data={'revision':row['revision']}).status_code==409
    assert client.get(docs+'/audit').status_code==200


def test_admin_all_sections_import_preview_no_token_csrf(opened):
    client,_,_=opened
    for path in ['/admin','/admin/tcc','/admin/dictionaries/template']:
        # The actual Excel template route is checked separately below.
        if path.endswith('/template'):continue
        assert client.get(path).status_code==200
    assert client.get('/admin/login',follow_redirects=False).status_code==303
    from app.routers.admin import router
    template=next(r.path for r in router.routes if r.name=='dictionary_template')
    assert client.get(template).status_code==200
    preview=next(r.path for r in router.routes if r.name=='import_preview')
    result=client.post(preview,files={'file':('names.xlsx',workbook([('names_male',dictionary_data())]),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')},data={'mode':'add'})
    assert result.status_code==200


def test_protection_can_be_restored_and_existing_users_not_modified(opened,monkeypatch):
    client,pid,factory=opened
    shared=client.get('/auth/me').json()
    with factory() as db:
        before=db.get(User,shared['id']).password_hash
    monkeypatch.setenv('PROJECT2_AUTH_ENABLED','1')
    assert client.get('/auth/me').status_code in (401,403)
    assert client.get('/admin').status_code==503
    with factory() as db:assert db.get(User,shared['id']).password_hash==before

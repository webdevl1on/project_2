"""Real cookie MFA and the existing handlers: no direct-ID/category/list/file escapes."""
from datetime import date as D
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.database.db import get_db
from app.models import User,PersonAssignment,PersonDocument
from app.models.access import AccessRule,AccessAudit
from app.services import documents,document_files,medical,accounts,access
from app.services.document_storage import DocumentStorage
from tests.test_access_control import acl_store,rule,PASSWORD
from tests.mfa_helpers import finish_http

@pytest.fixture
def web(acl_store,tmp_path,monkeypatch):
    db,ids,factory=acl_store
    documents.seed_types(db);db.commit()
    pid=ids['people'][1]
    doc=documents.save(db,ids['admin'],pid,'military',{'number':'SECRET-DOCUMENT-221'})
    path=tmp_path/'private';monkeypatch.setenv('PROJECT2_DOCUMENT_STORAGE',str(path))
    fid=document_files.attach(db,ids['admin'],pid,doc,db.get(PersonDocument,doc).revision,b'%PDF-1.7 protected','secret.pdf','front',storage=DocumentStorage(path))
    exam=medical.save(db,ids['admin'],pid,'exams',{'status':'COMPLETED','basis':'OTHER','issued_on':'2026-01-01','number':'MED-SECRET','fitness':'FIT','diagnosis':'SECRET-DIAGNOSIS'})['id']
    ids.update(document=doc,file=fid,exam=exam)
    def override():
        with factory() as session:yield session
    previous=dict(app.dependency_overrides);app.dependency_overrides[get_db]=override
    with TestClient(app,base_url='https://testserver') as client:yield client,db,ids,factory
    app.dependency_overrides.clear();app.dependency_overrides.update(previous)

def sign_in(client,who='user'):
    client.cookies.clear();response=finish_http(client,client.post('/auth/login',json={'username':'acl-'+who,'password':PASSWORD}));assert response.status_code==200,response.text
    return {'X-CSRF-Token':response.json()['csrf_token']}


def test_master_no_subject_access_but_can_manage_security_and_admin_has_all(web):
    client,db,i,_=web
    sign_in(client,'master')
    for path in [f'/persons/{i["people"][1]}/medical',f'/persons/{i["people"][1]}/documents',f'/person_full_info/{i["people"][1]}']:
        assert client.get(path).status_code==403
    assert client.get('/admin/users').status_code==200
    assert client.get('/admin/access').status_code==200
    assert client.get('/admin').status_code==200
    sign_in(client,'admin');assert client.get(f'/persons/{i["people"][1]}/medical').status_code==200


def test_user_no_rights_sees_no_people_no_positions_and_no_foreign_id(web):
    client,db,i,_=web;headers=sign_in(client)
    people=client.get('/persons');assert people.status_code==200 and 'Підлеглий' not in people.text and 'Сторонній' not in people.text
    table=client.get('/person-positions');assert table.status_code==200 and 'SECRET' not in table.text and 'position:2' not in table.text
    for path in [f'/person_full_info/{i["people"][1]}',f'/persons/{i["people"][1]}/documents/files/{i["file"]}',f'/events/presence?person_id={i["people"][1]}&on=2026-01-01']:
        assert client.get(path).status_code==403
    response=client.post('/person-positions/assign/prepare',headers=headers,data={'position_id':i['positions'][1],'person_id':i['people'][1],'on':'2026-01-01','actor_user_id':i['admin']})
    assert response.status_code==403


def test_basic_projection_does_not_leak_tax_birth_medical_or_family(web):
    client,db,i,_=web
    rule(db,i,unit=i['company']);headers=sign_in(client)
    person=client.get(f'/person_full_info/{i["people"][1]}');assert person.status_code==200,person.text
    assert 'Підлеглий Тест' in person.text and '0000000002' not in person.text and 'SECRET' not in person.text
    assert 'data-medical-panel' not in person.text and 'data-document-panel' not in person.text and 'data-additional-panel="family"' not in person.text
    assert client.get(f'/persons/{i["people"][1]}/medical').status_code==403
    assert client.get(f'/persons/{i["people"][1]}/profile-records/family').status_code==403
    page=client.get('/persons?sort_by=tax_number');assert '0000000002' not in page.text and 'Сторонній' not in page.text


def test_documents_read_write_and_files_share_the_same_scoped_permission(web):
    client,db,i,_=web
    rule(db,i,'documents',unit=i['child']);headers=sign_in(client)
    response=client.get(f'/persons/{i["people"][1]}/documents');assert response.status_code==200 and 'SECRET-DOCUMENT-221' in response.text
    catalog=client.get(f'/persons/{i["people"][1]}/documents/catalog').json();assert not catalog['can_edit'] and not catalog['can_history']
    response=client.get(f'/persons/{i["people"][1]}/documents/files/{i["file"]}');assert response.status_code==200 and response.content.startswith(b'%PDF')
    assert client.get(f'/persons/{i["people"][2]}/documents/files/{i["file"]}').status_code==403
    assert client.post(f'/persons/{i["people"][1]}/documents/{i["document"]}/archive',headers=headers,json={'revision':1}).status_code==403
    rule(db,i,'documents','edit',unit=i['child']);headers=sign_in(client)
    result=client.post(f'/persons/{i["people"][1]}/documents',headers=headers,json={'type':'other','values':{'number':'USER-ALLOWED'}})
    assert result.status_code==200,result.text


def test_medical_document_does_not_escape_through_general_file_api(web):
    client,db,i,_=web;pid=i['people'][1]
    from app.models import MedicalExam
    linked=medical.link_document(db,i['admin'],pid,'exams',i['exam'],'other',revision=db.get(MedicalExam,i['exam']).revision)
    fid=document_files.attach(db,i['admin'],pid,linked,db.get(PersonDocument,linked).revision,b'%PDF-1.7 medical','private-medical.pdf','front')
    rule(db,i,'documents',unit=i['child']);headers=sign_in(client)
    assert 'private-medical.pdf' not in client.get(f'/persons/{pid}/documents').text
    assert client.get(f'/persons/{pid}/documents/files/{fid}').status_code==403
    rule(db,i,'medical',unit=i['child'])
    assert client.get(f'/persons/{pid}/documents/files/{fid}').status_code==200


def test_matrix_csrf_fresh_mfa_actor_and_protected_roles(web):
    client,db,i,factory=web;headers=sign_in(client,'admin')
    state=client.get('/admin/access/data',params={'user_id':i['user']});assert state.status_code==200,state.text
    changes=[{'scope_type':'unit','unit_id':i['company'],'category':'basic','action':'read','effect':'ALLOW'}]
    body={'revision':state.json()['user']['revision'],'changes':changes,'reason':'Дозволено після перевірки','actor_user_id':i['master']}
    assert client.post(f'/admin/access/users/{i["user"]}/matrix',json=body).status_code==403
    assert client.post(f'/admin/access/users/{i["user"]}/matrix',headers={**headers,'Origin':'https://evil.example'},json=body).status_code==403
    saved=client.post(f'/admin/access/users/{i["user"]}/matrix',headers=headers,json=body);assert saved.status_code==200,saved.text
    with factory() as session:assert session.scalar(select(AccessAudit).where(AccessAudit.operation=='matrix_change')).actor_user_id==i['admin']
    assert client.post(f'/admin/access/users/{i["admin"]}/matrix',headers=headers,json={**body,'revision':1}).status_code==403
    sign_in(client)
    assert client.get('/admin/access').status_code==403
    assert client.get('/admin/access/explain',params={'user_id':i['admin'],'category':'basic'}).status_code==403


def test_staff_columns_facets_dates_and_picker_do_not_leak_denied_values(web):
    client,db,i,_=web
    rule(db,i,'service',unit=i['company']);rule(db,i,'basic',unit=i['company']);headers=sign_in(client)
    response=client.get('/person-positions?as_of=2026-01-01&sort_by=tax_number');assert response.status_code==200,response.text
    assert '0000000002' not in response.text and 'SECRET-DIAGNOSIS' not in response.text and 'Сторонній' not in response.text
    response=client.get('/person-positions?as_of=2026-01-01&tax_number=0000000002');assert response.status_code==200
    assert 'position:2' not in response.text
    response=client.get(f'/persons/{i["people"][1]}/medical');assert response.status_code==403


def test_new_user_role_and_account_changes_do_not_bypass_mfa(web):
    client,db,i,_=web
    pending=client.post('/auth/login',json={'username':'acl-user','password':PASSWORD});assert pending.status_code==200
    assert client.get('/persons',follow_redirects=False).status_code==401
    assert client.get('/admin/access/data',params={'user_id':i['admin']}).status_code==401


def test_explicit_create_initial_aggregate_and_error_forms_preserve_category_boundary(web):
    client,db,i,_=web
    from app.models import Rank
    from app.models.reference_data.ranks import ReferenceRanks
    db.add(Rank(**ReferenceRanks.RANKS[0]));db.commit()
    rule(db,i,'personal','create');headers=sign_in(client)
    created=client.post('/persons/new',headers=headers,data={'sex':'male','surname':'Створений','name':'Тест','surname_genitive':'Створеного','rank_id':'1'},follow_redirects=False)
    assert created.status_code==303,created.text
    assert client.get(created.headers['location']).status_code==200
    rule(db,i,'personal','edit',person=i['people'][1]);rule(db,i,'basic',person=i['people'][1])
    response=client.post(f'/persons/{i["people"][1]}/edit',headers=headers,data={'surname':'Підлеглий','name':'Тест','birth_day':'31','birth_month':'02','birth_year':'2001'})
    assert response.status_code==400,response.text
    assert '0000000002' not in response.text and 'readonly' in response.text


def test_scoped_organizational_excel_does_not_require_system_admin(web):
    from tests.test_organization_import import excel
    client,db,i,_=web
    rule(db,i,'organization','import',unit=i['child']);rule(db,i,'organization',unit=i['child']);headers=sign_in(client)
    content=excel([(['Взвод'],9,'Нова тестова посада')])
    r=client.post('/admin/organization/staff/preview',headers=headers,data={'scope_id':i['child'],'mode':'add','on':'2026-01-01'},files={'file':('staff.xlsx',content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert r.status_code==200,r.text
    assert 'assignment_order_number' not in r.text and 'person_id' not in r.text
    denied=client.post('/admin/organization/staff/preview',headers=headers,data={'scope_id':i['outside'],'mode':'add','on':'2026-01-01'},files={'file':('staff.xlsx',content,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
    assert denied.status_code==403,denied.text

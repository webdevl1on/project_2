"""Organization staffing UI/API with real MFA and isolated synthetic SQLite."""
from tests.access_helpers import legacy_user
from datetime import date as D
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from app.database.base import Base
from app.database.db import get_db
from app.main import app
from app.models import StaffStructure,StaffVersion,Position,Person,PersonAssignment,OrgCoverage,OrgStaffImport,OrgReassignment,OrgAudit
from app.services import accounts,organization,organization_staff
from app.services.staff_service import StaffService
from tests.mfa_helpers import finish_http
from tests.test_organization_import import fields,excel

@pytest.fixture
def web(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'admin-org-staff.sqlite3'),connect_args={'check_same_thread':False});Base.metadata.create_all(engine);factory=sessionmaker(engine)
    with factory() as db:
        actor=legacy_user(db,'org-staff-admin','Admin','synthetic-password','admin')
        legacy_user(db,'org-staff-viewer','User без прав','synthetic-password','user',actor_id=actor)
        root=organization.OrganizationService.create(db,actor,'battalion','Батальйон',D(2020,1,1))
        company=organization.OrganizationService.create(db,actor,'company','1 рота',D(2020,1,1),parent_id=root)
        child=organization.OrganizationService.create(db,actor,'platoon','1 взвод',D(2020,1,1),parent_id=company)
        structure=StaffStructure(org_unit_id=root,code='test',name='Базова структура');db.add(structure);db.flush()
        version=StaffVersion(staff_structure_id=structure.id,name='Базовий штат',valid_from=D(2020,1,1));db.add(version);db.flush()
        for u in (root,company,child):db.add(OrgCoverage(org_unit_id=u,staff_version_id=version.id,valid_from=D(2020,1,1)))
        positions=[]
        for number,u in [(1,company),(2,child)]:
            p=Position(staff_version_id=version.id,org_unit_id=u,**fields(number));db.add(p);positions.append(p)
        person=Person();db.add(person);db.commit()
        ids={'actor':actor,'root':root,'company':company,'child':child,'version':version.id,'structure':structure.id,'positions':[p.position_id for p in positions],'person':person.person_id}
    def override():
        with factory() as db:yield db
    previous=dict(app.dependency_overrides);app.dependency_overrides[get_db]=override
    with TestClient(app,base_url='https://testserver') as client:yield client,factory,ids
    app.dependency_overrides.clear();app.dependency_overrides.update(previous);engine.dispose()


def login(client,role='admin'):
    result=finish_http(client,client.post('/auth/login',json={'username':'org-staff-'+role,'password':'synthetic-password'}));assert result.status_code==200,result.text
    return {'X-CSRF-Token':result.json()['csrf_token']}


def preview(client,headers,scope,mode,rows,**extra):
    return client.post('/admin/organization/staff/preview',headers=headers,data={'scope_id':scope,'mode':mode,'on':'2026-01-01',**extra},files={'file':('positions.xlsx',excel(rows),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})


def test_staff_page_admin_security_template_and_explicit_mappings(web):
    client,factory,ids=web;path=f'/admin/organization/staff?unit_id={ids["company"]}&on=2026-01-01'
    assert client.get(path).status_code==401
    headers=login(client,'viewer');assert client.get(path).status_code==403
    client.cookies.clear();headers=login(client)
    response=client.get(path);assert response.status_code==200 and 'Потребують перепризначення' in response.text and 'стрілець' in response.text
    template=client.get('/admin/organization/staff/template');assert template.status_code==200
    assert client.post('/admin/organization/staff/map-positions',json={}).status_code==403
    assert client.post('/admin/organization/staff/map-positions',json={},headers={**headers,'Origin':'https://evil.example'}).status_code==403


def test_preview_partial_resume_and_explicit_conflict_resolution(web):
    client,factory,ids=web;headers=login(client)
    response=preview(client,headers,ids['company'],'add',[(['1 рота','1 взвод'],3,'Оператор'),(['1 рота'],1,'Нова назва')]);assert response.status_code==200,response.text
    with factory() as db:assert db.scalar(select(func.count()).select_from(OrgStaffImport))==0
    token=response.json()['token'];result=client.post('/admin/organization/staff/confirm',headers=headers,json={'token':token,'selected_rows':[3]});assert result.status_code==200,result.text
    receipt=result.json()['receipt'];key=receipt['id'];assert [r['status'] for r in receipt['rows']]==['accepted','conflict']
    assert client.post(f'/admin/organization/staff/imports/{key}/confirm',headers=headers,json={'selected_rows':[3]}).status_code==200
    conflict=receipt['rows'][1]
    resolved=client.post(f'/admin/organization/staff/imports/{key}/resolve',headers=headers,json={'row_number':4,'decision':'correct','revision':conflict['revision'],'reason':'Звірено з документом','actor_id':9999})
    assert resolved.status_code==200,resolved.text
    with factory() as db:
        assert db.get(Position,ids['positions'][0]).name_short=='нова назва'
        assert db.scalar(select(func.count()).select_from(Position))==3
        assert all(a.actor_user_id==ids['actor'] for a in db.scalars(select(OrgAudit)))


def test_preview_is_bound_to_personal_session(web):
    client,factory,ids=web;headers=login(client)
    result=preview(client,headers,ids['company'],'add',[(['1 рота'],3,'Оператор')]);token=result.json()['token']
    headers=login(client)
    response=client.post('/admin/organization/staff/confirm',headers=headers,json={'token':token,'selected_rows':[3]})
    assert response.status_code==409 and 'сесії' in response.text


def test_official_clone_is_vacant_and_default_table_uses_effective_composite(web):
    client,factory,ids=web;headers=login(client)
    response=preview(client,headers,ids['child'],'official',[(['1 взвод'],2,'Оператор')],name='Ротна версія');assert response.status_code==200,response.text
    result=client.post('/admin/organization/staff/confirm',headers=headers,json={'token':response.json()['token'],'selected_rows':[3]});assert result.status_code==200,result.text
    with factory() as db:
        assert db.get(StaffVersion,ids['version']).valid_to is None
        assert db.scalar(select(func.count()).select_from(PersonAssignment))==0
        effective=organization_staff.snapshot(db,ids['company'],D(2026,1,1))['positions'];assert {p.position_number for p in effective}=={1,2}
        assert all(p.position_id not in ids['positions'] for p in effective)
    page=client.get('/person-positions?as_of=2026-01-01');assert page.status_code==200 and 'Сукупний чинний штат' in page.text


def test_replace_queue_reassigns_actual_dates_without_fake_transfer(web):
    client,factory,ids=web;headers=login(client)
    with factory() as db:original=StaffService.create_assignment(db,ids['person'],ids['positions'][1],D(2021,1,2),order_number='21',order_date=D(2021,1,1),actor_id=ids['actor'])
    response=preview(client,headers,ids['company'],'replace',[(['1 рота','1 взвод'],2,'Правильна посада')]);assert response.status_code==200,response.text
    result=client.post('/admin/organization/staff/confirm',headers=headers,json={'token':response.json()['token'],'selected_rows':[3],'replace_ids':[ids['positions'][1]],'reason':'Помилковий імпорт','confirm_removal':True});assert result.status_code==200,result.text
    with factory() as db:
        q=db.scalar(select(OrgReassignment));qid,revision,pos=q.id,q.revision,q.replacement_position_id
        assert db.get(PersonAssignment,original).annulled_at is not None
    result=client.post(f'/admin/organization/staff/reassign/{qid}',headers=headers,json={'revision':revision,'position_id':pos,'assigned_from':'2021-01-02','order_number':'21','order_date':'2021-01-01','confirmed':True})
    assert result.status_code==200,result.text
    with factory() as db:
        assert db.get(OrgReassignment,qid).resolved_assignment_id==result.json()['assignment_id']
        row=db.get(PersonAssignment,result.json()['assignment_id']);assert row.assigned_from==D(2021,1,2) and row.assignment_order_number=='21' and row.person_id==ids['person']
        assert db.get(PersonAssignment,original).annulled_at


def test_withdraw_official_allows_corrected_version_without_deleting_old(web):
    client,factory,ids=web;headers=login(client)
    response=preview(client,headers,ids['company'],'official',[(['1 рота'],1,'Нова посада')],name='Помилкова');result=client.post('/admin/organization/staff/confirm',headers=headers,json={'token':response.json()['token'],'selected_rows':[3]});assert result.status_code==200,result.text
    key=result.json()['receipt_id'];version=result.json()['receipt']['version_id']
    withdrawn=client.post(f'/admin/organization/staff/imports/{key}/withdraw',headers=headers,json={'confirmed':True,'reason':'Помилковий файл'});assert withdrawn.status_code==200,withdrawn.text
    with factory() as db:assert db.get(StaffVersion,version).annulled_at
    next_preview=preview(client,headers,ids['company'],'official',[(['1 рота'],1,'Правильна посада')],name='Виправлена');assert next_preview.status_code==200,next_preview.text
    next_result=client.post('/admin/organization/staff/confirm',headers=headers,json={'token':next_preview.json()['token'],'selected_rows':[3]});assert next_result.status_code==200,next_result.text

"""Organization GUI/HTTP boundaries with genuine synthetic MFA sessions."""
from tests.access_helpers import legacy_user
from datetime import date
import pytest
from fastapi import FastAPI,Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.orm import sessionmaker
from lxml import html
from app.database.base import Base
from app.database.db import get_db
from app.models.organization import OrgUnit,OrgAudit
from app.routers.organization import router
from app.security.application import application_access
from app.services import accounts
from tests.mfa_helpers import login


@pytest.fixture
def organization_client(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'organization-http.sqlite3'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine)
    with factory() as db:
        admin=legacy_user(db,'org-admin','Тестовий Admin','synthetic-org-password','admin')
        viewer=legacy_user(db,'org-viewer','Тестовий User без прав','synthetic-org-password','user',actor_id=admin)
        token,csrf=login(db,'org-admin','synthetic-org-password')
        viewer_token,viewer_csrf=login(db,'org-viewer','synthetic-org-password')
    test_app=FastAPI(dependencies=[Depends(application_access)])
    test_app.include_router(router)
    def override():
        with factory() as db:yield db
    test_app.dependency_overrides[get_db]=override
    with TestClient(test_app,base_url='https://testserver') as client:
        client.cookies.set('project2_user',token);client.headers['X-CSRF-Token']=csrf
        yield client,factory,{'admin':admin,'viewer':viewer,'viewer_token':viewer_token,'viewer_csrf':viewer_csrf,'token':token,'csrf':csrf}
    engine.dispose()


def create(client,name,kind='company',parent_id=None,on='2026-01-01'):
    response=client.post('/admin/organization/units',json={'name':name,'kind':kind,'formed_on':on,'parent_id':parent_id})
    assert response.status_code==200,response.text
    return response.json()['unit_id']


def state(client,on='2026-06-01'):
    response=client.get('/admin/organization/tree',params={'on':on});assert response.status_code==200,response.text
    return response.json()


def revision(client,key):return client.get(f'/admin/organization/units/{key}').json()['unit']['revision']


def test_admin_page_has_distinct_dated_forms_and_shared_components(organization_client):
    client,_,_=organization_client
    page=client.get('/admin/organization?on=2026-06-01');assert page.status_code==200
    doc=html.fromstring(page.text)
    assert doc.xpath('//*[@data-org-tree]') and doc.xpath('//*[@data-org-form="create"]')
    assert {node.get('data-org-form') for node in doc.xpath('//*[@data-org-form]')}=={'create','name','level','parent','operational','dissolve','annul'}
    assert '/static/js/profile_dates.js' in page.text and '/static/js/security_session.js' in page.text
    assert doc.xpath('//input[@name="on" and @value="2026-06-01"]')
    assert doc.xpath('//*[@data-org-roster-panel]')


def test_routes_deny_anonymous_viewer_wrong_csrf_and_forged_actor(organization_client):
    client,factory,ids=organization_client
    response=client.post('/admin/organization/units',json={'kind':'company','name':'3 рота','formed_on':'2026-01-01','actor_id':ids['viewer']},headers={'X-CSRF-Token':'wrong'})
    assert response.status_code==403
    key=create(client,'3 рота')
    with factory() as db:assert db.scalar(select(OrgAudit).where(OrgAudit.org_unit_id==key)).actor_user_id==ids['admin']
    client.cookies.clear();client.cookies.set('project2_user',ids['viewer_token']);client.headers['X-CSRF-Token']=ids['viewer_csrf']
    assert client.get('/admin/organization').status_code==403
    assert client.post('/admin/organization/units',json={'kind':'company','name':'Заборонено','formed_on':'2026-01-01'}).status_code==403
    client.cookies.clear();assert client.get('/admin/organization').status_code==401


def test_create_parent_later_and_rename_use_effective_dates(organization_client):
    client,_,_=organization_client
    child=create(client,'1 взвод','platoon')
    parent=create(client,'3 рота')
    result=client.post(f'/admin/organization/units/{child}/parent',json={'revision':revision(client,child),'parent_id':parent,'effective_from':'01.03.2026'})
    assert result.status_code==200,result.text
    before=next(node for node in state(client,'2026-02-28')['units'] if node['id']==child)
    after=next(node for node in state(client,'2026-03-01')['units'] if node['id']==child)
    assert before['parent_id'] is None and after['parent_id']==parent
    response=client.post(f'/admin/organization/units/{child}/name',json={'revision':revision(client,child),'name':'Взвод БпЛА','effective_from':'2026-04-01'})
    assert response.status_code==200,response.text
    history=client.get(f'/admin/organization/units/{child}').json()
    assert [row['name'] for row in history['states']]==['1 взвод','1 взвод','Взвод БпЛА']


def test_validation_conflict_does_not_redirect_or_mutate_existing_values(organization_client):
    client,_,_=organization_client
    key=create(client,'Чинна рота');rev=revision(client,key)
    response=client.post(f'/admin/organization/units/{key}/name',json={'revision':rev,'name':'Збережена чернетка','effective_from':'31.02.2026'})
    assert response.status_code==422 and response.json()['field']=='effective_from'
    assert 'location' not in response.headers
    assert client.get(f'/admin/organization/units/{key}').json()['states'][0]['name']=='Чинна рота'
    assert revision(client,key)==rev
    other=create(client,'Інша рота')
    result=client.post(f'/admin/organization/units/{other}/name',json={'revision':revision(client,other),'name':'Чинна рота','effective_from':'2026-02-01'})
    assert result.status_code==409 and 'location' not in result.headers
    assert client.get(f'/admin/organization/units/{other}').json()['states'][0]['name']=='Інша рота'


def test_sibling_reorder_rejects_cross_parent_and_stale_revision(organization_client):
    client,_,_=organization_client
    a=create(client,'1 рота');b=create(client,'2 рота');child=create(client,'Взвод','platoon',a)
    response=client.post('/admin/organization/reorder',json={'on':'2026-06-01','parent_id':None,'ids':[a,child,b],'revisions':{str(key):revision(client,key) for key in [a,b,child]}})
    assert response.status_code==409
    revisions={str(key):revision(client,key) for key in [a,b]}
    response=client.post('/admin/organization/reorder',json={'on':'2026-06-01','parent_id':None,'ids':[b,a],'revisions':revisions});assert response.status_code==200,response.text
    response=client.post('/admin/organization/reorder',json={'on':'2026-06-01','parent_id':None,'ids':[a,b],'revisions':revisions});assert response.status_code==409
    assert next(node for node in state(client)['units'] if node['id']==child)['parent_id']==a


def test_operational_parent_is_independent_and_can_be_closed(organization_client):
    client,_,_=organization_client
    parent=create(client,'Батальйон','battalion');child=create(client,'Рота')
    response=client.post(f'/admin/organization/units/{child}/operational',json={'revision':revision(client,child),'parent_id':parent,'valid_from':'2026-03-01','note':'Тимчасово'})
    assert response.status_code==200,response.text
    detail=client.get(f'/admin/organization/units/{child}').json();edge=detail['operational'][0]
    response=client.post(f'/admin/organization/operational/{edge["id"]}/close',json={'revision':edge['revision'],'valid_to':'2026-04-30'})
    assert response.status_code==200,response.text
    node=next(node for node in state(client,'2026-04-01')['units'] if node['id']==child)
    assert node['parent_id'] is None and node['operational_parent_id']==parent
    node=next(node for node in state(client,'2026-05-01')['units'] if node['id']==child)
    assert node['operational_parent_id'] is None


def test_dissolution_and_annulment_are_explicit_separate_history_states(organization_client):
    client,factory,_=organization_client
    dissolved=create(client,'Розформована рота');annulled=create(client,'Помилкова рота')
    bad=client.post(f'/admin/organization/units/{annulled}/annul',json={'revision':revision(client,annulled),'reason':'Помилка'})
    assert bad.status_code==422
    done=client.post(f'/admin/organization/units/{dissolved}/dissolve',json={'revision':revision(client,dissolved),'dissolved_on':'2026-04-30','confirmed':True});assert done.status_code==200,done.text
    done=client.post(f'/admin/organization/units/{annulled}/annul',json={'revision':revision(client,annulled),'reason':'Помилка введення','confirmed':True});assert done.status_code==200,done.text
    with factory() as db:
        assert db.get(OrgUnit,dissolved).annulled_at is None and db.get(OrgUnit,dissolved).dissolved_on==date(2026,4,30)
        assert db.get(OrgUnit,annulled).annulled_at and db.get(OrgUnit,annulled).dissolved_on is None
    payload=state(client);assert not payload['units']
    assert {node['id'] for node in payload['inactive_units']}=={dissolved,annulled}


def test_http_rejects_inverse_hierarchy_and_requires_other_level(organization_client):
    client,_,_=organization_client
    platoon=create(client,'Взвод',kind='platoon')
    bad=client.post('/admin/organization/units',json={'name':'Полк у взводі','kind':'regiment','formed_on':'2026-01-01','parent_id':platoon})
    assert bad.status_code==409 and 'ієрархія' in bad.json()['detail']
    bad=client.post('/admin/organization/units',json={'name':'Інший','kind':'other','formed_on':'2026-01-01'})
    assert bad.status_code==409 and 'рівень' in bad.json()['detail']
    good=client.post('/admin/organization/units',json={'name':'Інший','kind':'other','hierarchy_level':6,'formed_on':'2026-01-01','parent_id':platoon})
    assert good.status_code==200

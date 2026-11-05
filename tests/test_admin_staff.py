from datetime import date as D
from fastapi.testclient import TestClient as AnonymousClient
from tests.http_auth import AuthenticatedClient as TestClient
from lxml import html
from app.main import app
from app.database.db import get_db
from app.models import StaffVersion
from tests.test_staff_history import store, setup, workbook


def test_admin_staff_forms_redirects_and_import(store,monkeypatch):
    monkeypatch.setenv('PROJECT2_AUTH_ENABLED','0')
    _,versions,positions,people=setup(store)
    def db():yield store
    app.dependency_overrides[get_db]=db
    try:
        with TestClient(app) as client:
            from app.routers import admin as admin_router, staff as staff_router
            paths=[route.path for route in [*admin_router.router.routes,*staff_router.router.routes] if hasattr(route,'path')]
            assert paths.count('/admin/staff')==1 and paths.count('/staff/import/preview')==1
            table=html.fromstring(client.get('/person-positions').text)
            history=html.fromstring(client.get('/staff/history').text)
            admin=html.fromstring(client.get('/admin/staff').text)
            assert not table.xpath('//form[@action="/staff/import/preview"]|//*[@id="staff-import-modal"]')
            assert not history.xpath('//form[starts-with(@action,"/staff/versions/") or starts-with(@action,"/staff/positions/") or @action="/staff/structures"]')
            assert history.xpath('//form[@action="/staff/assignments/create"]')
            assert len(admin.xpath('//form[@action="/staff/import/preview"]'))==1
            assert admin.xpath('//form[@action="/staff/structures"]')
            assert not admin.xpath('//form[starts-with(@action,"/staff/assignments/")]')
            assert '/admin/staff' in client.get('/admin').text
            result=client.post('/staff/structures',data={'code':'separate','name':'Окрема структура'},follow_redirects=False)
            assert result.status_code==303 and result.headers['location'].startswith('/admin/staff?structure_id=')
            assert not html.fromstring(client.get(result.headers['location']).text).xpath('//form[starts-with(@action,"/staff/positions/")]')
            v=versions[1];p=positions[1]
            result=client.post(f'/staff/versions/{v.id}/correct',data={'revision':v.revision,'name':'Уточнена','valid_from':'2026-06-01'},follow_redirects=False)
            assert result.status_code==303 and result.headers['location'].startswith('/admin/staff?')
            result=client.post(f'/staff/positions/{p.position_id}/correct',data={'revision':p.revision,'name_short':'Уточнена посада'},follow_redirects=False)
            assert result.status_code==303 and result.headers['location'].startswith('/admin/staff?')
            result=client.post('/staff/assignments/create',data={'person_id':people[0].person_id,'position_id':p.position_id,'assigned_from':'2026-06-01'},follow_redirects=False)
            assert result.status_code==303 and result.headers['location'].startswith('/staff/history?')
            rev=store.get(StaffVersion,v.id).revision
            assert client.post(f'/staff/versions/{v.id}/close',data={'revision':rev,'valid_to':'2026-09-01'}).status_code==409
            assert store.get(StaffVersion,v.id).valid_to is None
            result=client.post(f'/staff/versions/{v.id}/close',data={'revision':rev,'valid_to':'2026-09-01','confirmed':'true'},follow_redirects=False)
            assert result.status_code==303 and result.headers['location'].startswith('/admin/staff?')
            assert store.get(StaffVersion,v.id).valid_to==D(2026,9,1)
            preview=client.post('/staff/import/preview',data={'name':'Імпорт','valid_from':'2025-01-01','valid_to':'2025-12-31','structure_id':versions[0].staff_structure_id},files={'file':('staff.xlsx',workbook().getvalue())})
            token=html.fromstring(preview.text).xpath('//input[@name="token"]/@value')[0]
            done=client.post('/staff/import/confirm',data={'token':token},follow_redirects=False)
            assert done.status_code==303 and done.headers['location'].startswith('/admin/staff?version_id=')
            assert 'Відкрити штатку' in client.get(done.headers['location']).text
            assert client.post('/staff/import/confirm',data={'token':token}).status_code==409
    finally:app.dependency_overrides.clear()


def test_admin_staff_retains_admin_access(store,monkeypatch):
    monkeypatch.setenv('PROJECT2_AUTH_ENABLED','1');monkeypatch.delenv('PROJECT2_DEV_ADMIN_OPEN',raising=False)
    def db():yield store
    app.dependency_overrides[get_db]=db
    try:
        with AnonymousClient(app,base_url='https://testserver') as client:assert client.get('/admin/staff').status_code in (401,503)
    finally:app.dependency_overrides.clear()

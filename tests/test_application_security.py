"""Whole-application Security 1.1, with real sessions and isolated synthetic data."""
from datetime import datetime,UTC,timedelta
import re
import pytest
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from app.database.base import Base
from app.database.db import get_db
from app.main import app
from app.models import User,UserSession,Person
from app.services import accounts
from app.security.application import PUBLIC_ROUTES,application_access,safe_return


@pytest.fixture
def secure(tmp_path,monkeypatch):
    engine=create_engine('sqlite:///'+str(tmp_path/'security.sqlite3'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine)
    with factory() as db:
        a=accounts.create_user(db,'security_admin','Адміністратор тестів','synthetic-password','admin')
        e=accounts.create_user(db,'security_editor','Редактор тестів','synthetic-password','editor',actor_id=a)
        v=accounts.create_user(db,'security_viewer','Спостерігач тестів','synthetic-password','viewer',actor_id=a)
        p=Person(tax_number='0123456789');db.add(p);db.commit();pid=p.person_id
    def override():
        with factory() as db:yield db
    previous=dict(app.dependency_overrides);app.dependency_overrides[get_db]=override
    with TestClient(app,base_url='https://testserver') as client:
        yield client,factory,{'admin':a,'editor':e,'viewer':v},pid
    app.dependency_overrides.clear();app.dependency_overrides.update(previous);engine.dispose()


def login(client,role='editor'):
    response=client.post('/auth/login',json={'username':'security_'+role,'password':'synthetic-password'})
    assert response.status_code==200,response.text
    return response.json()['csrf_token']


def registered_routes():
    for route in app.routes:
        if hasattr(route,'effective_route_contexts'):yield from route.effective_route_contexts()
        else:yield route


def routes():
    return [(method,route.path) for route in registered_routes() if hasattr(route,'dependant') for method in sorted(route.methods)
            if (method,route.path) not in PUBLIC_ROUTES]


@pytest.mark.parametrize('method,path',routes())
def test_every_registered_route_denies_anonymous_before_read_or_write(secure,method,path):
    client,_,_,_=secure
    path=re.sub(r'\{[^}]+\}','1',path)
    response=client.request(method,path,json={} if method not in ('GET','HEAD') else None,follow_redirects=False)
    assert response.status_code==401,(method,path,response.status_code,response.text[:100])
    assert '0123456789' not in response.text


def test_registered_routes_have_central_policy_and_only_asset_mount(secure):
    from starlette.routing import Mount
    for route in registered_routes():
        if hasattr(route,'dependant'):assert any(d.call is application_access for d in route.dependant.dependencies),route.path
        elif isinstance(route,Mount):assert route.path=='/static'
        else:pytest.fail(f'Unprotected route: {route.path}')
    client,*_=secure
    assert client.get('/static/js/login.js').status_code==200
    assert client.get('/static/../data/private.pdf').status_code!=200


@pytest.mark.parametrize('flag',[None,'0','1','unexpected'])
def test_old_auth_flags_never_allow_anonymous_or_create_shared_user(secure,monkeypatch,flag):
    client,factory,_,_=secure
    if flag is None:monkeypatch.delenv('PROJECT2_AUTH_ENABLED',raising=False)
    else:monkeypatch.setenv('PROJECT2_AUTH_ENABLED',flag)
    for key in ('PROJECT2_DEV_AUTH_BYPASS','PROJECT2_DEV_ADMIN_OPEN'):monkeypatch.setenv(key,'1')
    for path in ('/auth/me','/persons','/admin','/staff/history'):
        assert client.get(path,follow_redirects=False).status_code==401
    with factory() as db:assert db.scalar(select(func.count()).select_from(User))==3


def test_html_redirect_api_401_login_and_safe_return(secure):
    client,_,_,_=secure
    response=client.get('/staff/history?version_id=1&q=27',headers={'Accept':'text/html'},follow_redirects=False)
    assert response.status_code==303 and response.headers['location'].startswith('/auth/login?return_to=')
    page=client.get(response.headers['location']);assert page.status_code==200 and 'Персональний вхід' in page.text
    assert '0123456789' not in page.text
    assert client.get('/events/data').status_code==401
    response=client.post('/auth/login',json={'username':'security_editor','password':'synthetic-password','return_to':'/staff/history?version_id=1&q=27'})
    assert response.status_code==200 and response.json()['redirect_to']=='/staff/history?version_id=1&q=27'
    assert 'HttpOnly' in response.headers['set-cookie'] and 'Secure' in response.headers['set-cookie'] and 'SameSite=strict' in response.headers['set-cookie']
    assert client.get('/persons').status_code==200
    assert client.get('/persons').headers['cache-control']=='no-store'


@pytest.mark.parametrize('target',['https://evil.example','//evil.example','/\\evil.example','/%2f/evil.example','/%5cevil.example','/\r\nLocation:evil','/%250aevil','//[invalid','auth/login','/auth/login?return_to=/auth/login'])
def test_return_cannot_escape_local_application(target):
    assert safe_return(target)=='/persons'


@pytest.mark.parametrize('condition',['tampered','expired','revoked','disabled'])
def test_invalid_sessions_cannot_read_or_write(secure,condition):
    client,factory,ids,_=secure;csrf=login(client)
    if condition=='tampered':client.cookies.clear();client.cookies.set('project2_user','forged')
    else:
        with factory() as db:
            if condition=='expired':db.scalar(select(UserSession)).expires_at=datetime.now(UTC)-timedelta(seconds=1)
            elif condition=='revoked':db.delete(db.scalar(select(UserSession)))
            else:db.get(User,ids['editor']).is_active=False
            db.commit()
    assert client.get('/persons').status_code==401
    assert client.post('/staff/assignments/create',data={},headers={'X-CSRF-Token':csrf}).status_code==401


def test_roles_csrf_origin_and_legacy_admin_token(secure,monkeypatch):
    client,_,_,pid=secure
    csrf=login(client,'viewer')
    assert client.get('/persons').status_code==200
    assert client.get('/admin').status_code==403
    assert client.post(f'/persons/{pid}/personal-number',data={'personal_number':'x'},headers={'X-CSRF-Token':csrf}).status_code==403
    client.cookies.clear();csrf=login(client,'editor')
    assert client.get('/admin/staff').status_code==403
    assert client.post('/staff/structures',data={'code':'x','name':'x'},headers={'X-CSRF-Token':csrf}).status_code==403
    assert client.post(f'/persons/{pid}/personal-number',data={'personal_number':'test'}).status_code==403
    assert client.post(f'/persons/{pid}/personal-number',data={'personal_number':'test'},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert client.post(f'/persons/{pid}/personal-number',data={'personal_number':'test','csrf':csrf},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post(f'/persons/{pid}/personal-number',data={'personal_number':'test','csrf':csrf}).status_code==200
    assert client.post(f'/persons/{pid}/personal-number',json={},headers={'X-CSRF-Token':csrf}).status_code==200
    client.cookies.clear();csrf=login(client,'admin')
    assert client.get('/admin').status_code==200
    assert client.post('/staff/structures',data={'code':'security','name':'Тестова структура','csrf':csrf},follow_redirects=False).status_code==303
    assert client.post('/admin/login',data={'token':'x'*40,'csrf':csrf}).status_code==403
    assert client.post('/auth/logout',headers={'X-CSRF-Token':csrf}).status_code==200
    client.cookies.set('project2_admin','legacy-shared-token')
    assert client.get('/admin').status_code==401
    assert client.get('/persons').status_code==401


def test_all_unsafe_routes_require_csrf_before_subject_validation(secure):
    client,*_=secure;login(client,'admin')
    for method,path in routes():
        if method in ('GET','HEAD','OPTIONS'):continue
        path=re.sub(r'\{[^}]+\}','1',path)
        response=client.request(method,path,json={})
        assert response.status_code==403 and 'CSRF' in response.text,(method,path,response.text[:100])


def test_loopback_http_requires_explicit_flag_and_rejects_proxy_or_lan(secure,monkeypatch):
    client,*_=secure
    monkeypatch.setenv('PROJECT2_AUTH_ALLOW_LOCAL_HTTP','1')
    for host,peer,headers in [('localhost','127.0.0.1',{}),('127.0.0.1','127.0.0.1',{}),('[::1]','::1',{})]:
        with TestClient(app,base_url='http://localhost',headers={'Host':host},client=(peer,1234)) as local:
            assert local.get('/auth/login').status_code==200
            assert local.get('/persons').status_code==401
    for host,peer,headers in [('192.168.1.5','192.168.1.6',{}),('localhost','127.0.0.1',{'X-Forwarded-For':'192.168.1.6'}),('localhost','127.0.0.1',{'Via':'proxy'})]:
        with TestClient(app,base_url='http://'+host,client=(peer,1234)) as remote:assert remote.get('/auth/login',headers=headers).status_code==403


def test_explicit_cli_bootstrap_can_preserve_legacy_technical_users_only(tmp_path):
    from app.models import User
    engine=create_engine('sqlite:///'+str(tmp_path/'bootstrap.sqlite3'));Base.metadata.create_all(engine)
    with sessionmaker(engine)() as db:
        old=User(username='project2-open-access',display_name='Спільний автор — авторизацію вимкнено',role='admin',password_hash='open-access-only$synthetic')
        db.add(old);db.commit();old_id=old.id
        with pytest.raises(PermissionError):accounts.create_user(db,'personal-admin','Персональний адміністратор','synthetic-password','admin')
        key=accounts.create_user(db,'personal-admin','Персональний адміністратор','synthetic-password','admin',allow_legacy_bootstrap=True)
        assert key!=old_id and db.get(User,old_id).password_hash=='open-access-only$synthetic'
        with pytest.raises(PermissionError):accounts.create_user(db,'second-admin','Зайвий адміністратор','synthetic-password','admin',allow_legacy_bootstrap=True)
    engine.dispose()


def test_http_cannot_enable_cli_bootstrap_or_leak_password_in_get_form(secure):
    client,_,_,_=secure
    assert client.post('/auth/users',json={'username':'spoof','allow_legacy_bootstrap':True}).status_code==401
    html=client.get('/auth/login').text
    assert 'id="personal-login" method="post" action="/auth/login"' in html
    assert client.post('/auth/login',data={'username':'security_admin','password':'synthetic-password'}).status_code==415


@pytest.mark.parametrize('path',['/%73taff/structures','/staff/%69mport/preview','/%61dmin','/admin%2Fstaff'])
def test_encoded_administrative_paths_cannot_bypass_role(secure,path):
    client,*_=secure;csrf=login(client,'editor')
    response=client.get(path) if 'admin' in path or '%61dmin' in path else client.post(path,data={'csrf':csrf})
    assert response.status_code==403


def test_mount_prefix_cannot_bypass_administrative_role(secure):
    client,*_=secure;csrf=login(client,'editor')
    with TestClient(app,base_url='https://testserver',root_path='/base') as prefixed:
        prefixed.cookies.update(client.cookies)
        response=prefixed.post('/base/staff/structures',data={'code':'denied','name':'denied'},headers={'X-CSRF-Token':csrf})
        assert response.status_code==403


def test_html_accept_never_turns_json_or_file_denial_into_redirect(secure):
    client,*_=secure
    for path in ('/auth/me','/openapi.json','/events/data','/persons/1/documents/files/1','/admin/dictionaries/template.xlsx','/geography/search?kind=settlement&q=test'):
        response=client.get(path,headers={'Accept':'text/html'},follow_redirects=False)
        assert response.status_code==401 and 'location' not in response.headers,path

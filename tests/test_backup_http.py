"""Real MFA/CSRF and roles; no HTTP restore or archive download capability."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database.db import get_db
from app.services.backups import commands
from app.services.backups.store import Store
from app.services.backups.crypto import Keyring
from tests.test_access_control import acl_store,PASSWORD
from tests.test_access_http import sign_in
from tests.test_backups import backup_config
from types import SimpleNamespace

@pytest.fixture
def backup_web(acl_store,backup_config,monkeypatch):
    db,ids,factory=acl_store;c,_=backup_config;store=Store(c,Keyring(c.key_file))
    backend=SimpleNamespace(store=store,config=c,initialize=lambda:store.initialize())
    monkeypatch.setattr(commands,'backend',lambda db:backend)
    previous=dict(app.dependency_overrides)
    def override():
        with factory() as session:yield session
    app.dependency_overrides[get_db]=override
    with TestClient(app,base_url='https://testserver') as client:yield client,store,ids,factory
    app.dependency_overrides.clear();app.dependency_overrides.update(previous)


def test_backup_roles_csrf_fresh_mfa_and_server_author(backup_web):
    client,store,ids,factory=backup_web
    assert client.get('/admin/backups/data').status_code==401
    sign_in(client,'user');assert client.get('/admin/backups').status_code==403
    headers=sign_in(client,'admin');assert client.get('/admin/backups').status_code==200
    assert client.get('/admin/backups/data').json()['can_run']
    admin_job=client.post('/admin/backups/create',headers=headers)
    assert admin_job.status_code==202 and admin_job.json()['actor_user_id']==ids['admin']
    item=store.read('jobs',admin_job.json()['id']);item['state']='SUCCESS';store.save('jobs',item)
    headers=sign_in(client,'master')
    assert client.post('/admin/backups/create').status_code==403
    assert client.post('/admin/backups/create',headers={**headers,'Origin':'https://foreign.example'}).status_code==403
    result=client.post('/admin/backups/create',headers=headers,json={'actor_user_id':ids['admin']})
    assert result.status_code==202,result.text
    assert result.json()['actor_user_id']==ids['master']
    assert client.post('/admin/backups/create',headers=headers).json()['id']==result.json()['id']
    status=client.get('/admin/backups/data');assert 'secret-key' not in status.text and 'main-key' not in status.text and 'PROJECT2_MFA_KEYS' not in status.text
    from app.models import UserSession
    from sqlalchemy import select
    from datetime import timedelta
    with factory() as db:
        session=db.scalar(select(UserSession).where(UserSession.user_id==ids['master']));session.created_at-=timedelta(minutes=10);session.mfa_verified_at-=timedelta(minutes=6);db.commit()
    assert client.post('/admin/backups/create',headers=headers).status_code==403
    assert client.post('/admin/backups/restore',headers=headers).status_code==404
    assert client.get('/admin/backups/archive/file').status_code==404


def test_unconfigured_backup_status_is_safe_and_visible(acl_store,monkeypatch):
    monkeypatch.delenv('PROJECT2_BACKUP_CONFIG',raising=False)
    db,ids,_=acl_store
    result=commands.status(db,ids['master']);assert not result['configured'] and not result['can_run']

def test_three_audit_tabs_filters_export_and_subject_acl(backup_web):
    client,store,ids,factory=backup_web
    sign_in(client,'user')
    for path in ('/admin/audit','/admin/audit/export.txt','/admin/backups/volumes'):
        assert client.get(path).status_code==403
    sign_in(client,'admin')
    for tab in ('system','subject','backup'):
        result=client.get('/admin/audit',params={'tab':tab,'sort1':'actor','dir1':'asc','sort2':'at','dir2':'desc'})
        assert result.status_code==200,result.text
        assert 'data-column-table' in result.text
        export=client.get('/admin/audit/export.txt',params={'tab':tab})
        assert export.status_code==200 and export.headers['content-type'].startswith('text/plain')
        assert 'Логін автора' in export.text
    from app.models import Person
    with factory() as db:
        person=db.get(Person,ids['people'][0]);person.personal_number='SECRET-SYNTHETIC-ACL-VALUE';db.commit()
    assert 'SECRET-SYNTHETIC-ACL-VALUE' in client.get('/admin/audit',params={'tab':'subject','q':'SECRET-SYNTHETIC-ACL-VALUE'}).text
    sign_in(client,'master')
    for path in ('/admin/audit','/admin/audit/export.txt'):
        result=client.get(path,params={'tab':'subject','q':'SECRET-SYNTHETIC-ACL-VALUE'})
        assert result.status_code==200
        payload=result.text.split('<tbody>')[1].split('</tbody>')[0] if path=='/admin/audit' else result.text
        assert 'SECRET-SYNTHETIC-ACL-VALUE' not in payload
    assert client.get('/admin/audit?sort=unknown').status_code==422

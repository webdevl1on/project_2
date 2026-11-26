"""Real MFA/CSRF and roles; no HTTP restore or archive download capability."""
import pytest
from tests.http_auth import LoopbackClient as TestClient
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


def test_panel_status_projects_versions_jobs_and_events_without_private_metadata(backup_web, monkeypatch):
    from app.services.backups import windows_storage

    client, store, ids, _ = backup_web
    summer = '2026-07-01T15:05:00+00:00'
    winter = '2026-11-01T15:05:00+00:00'
    newer = '2026-11-02T15:06:00+00:00'
    private = {
        'path': r'C:\private\archive',
        'volume_id': r'\\?\Volume{12345678-0000-1111-2222-123456789abc}\dummy',
        'sid': 'S-1-5-21-55555-1010',
        'sha256': 'f' * 64,
        'key': 'PRIVATE_SYNTHETIC_KEY',
    }
    source_id = 'a' * 32
    store.initialize()
    for folder in ('emergency', 'statistics'):
        (store.root / folder).mkdir()
    store.save('emergency', {'id': source_id, 'at': summer, 'day': '2026-07-01', 'ready': True,
                             'books': {'first': {'size': 10}}, 'files': [private], **private})
    store.save('emergency', {'id': 'b' * 32, 'at': newer, 'day': '2026-11-02', 'ready': True,
                             'books': {'first': {'size': 10}, 'second': {'size': 15}},
                             'file_count': 7, **private})
    backup_id = 'c' * 32
    for catalog_id, at, drill in ((backup_id, winter, 'NOT_RUN'), ('d' * 32, summer, 'SUCCESS')):
        store.save('catalog', {'id': catalog_id, 'snapshot_at': at, 'kind': 'full', 'size': 2048,
                               'integrity': 'VERIFIED', 'external': 'NOT_CONFIGURED', 'drill': drill, **private})
        (store.root / (catalog_id + '.p2b')).touch()
        (store.config.secrets / (catalog_id + '.p2s')).touch()
    store.save('statistics', {'id': '1' * 32, 'at': summer, 'backups': {'size': 10, **private},
                              'excel': {'size': 20}, 'documents': {'size': 30}, **private})
    job_id = 'e' * 32
    usb_details = {'files': 13, 'version': f'2026-07-01_180459_{source_id}_usb_{job_id}', **private}
    store.save('jobs', {'id': job_id, 'at': summer, 'completed_at': winter, 'state': 'SUCCESS', 'operation': 'usb',
                        'details': {'volume_id': 'opaque-volume-token', **{k: v for k, v in private.items() if k != 'volume_id'}},
                        'result': usb_details})
    for n in range(5):
        store.save('jobs', {'id': f'{n + 2:032x}', 'at': newer, 'scheduled': True,
                            'state': 'SUCCESS', 'operation': 'statistics'})
    running = '9' * 32
    store.save('jobs', {'id': running, 'at': summer, 'operation': 'create', 'state': 'RUNNING',
                        'authorized_at': winter, 'details': private})
    monkeypatch.setattr(windows_storage, 'cached_volumes', lambda engine: [
        {**private, 'id': 'opaque-volume-token', 'label': 'P2-EMERGENCY'},
    ])
    store.event('restore', 'SUCCESS', details={'files': 2, **private})

    sign_in(client, 'user')
    assert client.get('/admin/backups/data', params={'job': job_id}).status_code == 403
    for role in ('master', 'admin'):
        sign_in(client, role)
        response = client.get('/admin/backups/data', params={'job': job_id})
        assert response.status_code == 200
        data = response.json()
        assert data['last_full']['snapshot_at_kyiv'] == '01.11.2026 17:05'
        assert data['last_full']['drill'] == 'NOT_RUN' and data['last_full']['size'] == 2048
        assert data['last_success']['snapshot_at_kyiv'] == '01.07.2026 18:05'
        assert data['emergency']['at_kyiv'] == '02.11.2026 17:06'
        assert data['emergency']['size'] == 25 and data['emergency']['file_count'] == 7
        assert data['last_usb'] == {'at': winter, 'at_kyiv': '01.11.2026 17:05', 'label': 'P2-EMERGENCY',
                                    'excel_at': summer, 'excel_at_kyiv': '01.07.2026 18:05', 'files': 13,
                                    'outdated': True}
        assert len(data['jobs']) == 5 and data['watched_jobs'][0]['id'] == job_id
        assert [item['id'] for item in data['active_jobs']] == [running]
        assert 'authorization_expires_at' not in data['active_jobs'][0]
        assert data['events'][-1]['details'] == {'files': 2}
        for field in (*private.values(), 'opaque-volume-token'):
            assert field not in response.text and field not in client.get('/admin/backups').text
    monkeypatch.setattr(windows_storage, 'cached_volumes', lambda engine: [
        {'id': 'opaque-volume-token', 'label': private['sid']},
    ])
    assert client.get('/admin/backups/data').json()['last_usb']['label'] is None


def test_panel_projects_usb_success_event_before_job_is_finalized(backup_web, monkeypatch):
    from app.services.backups import windows_storage

    client, store, _, _ = backup_web
    store.initialize()
    version, job = 'a' * 32, 'b' * 32
    (store.root / 'emergency').mkdir()
    stamp = '2026-07-01T15:05:00+00:00'
    store.save('emergency', {'id': version, 'at': stamp, 'ready': True, 'books': {}, 'files': []})
    store.save('jobs', {'id': job, 'at': stamp, 'operation': 'usb', 'state': 'RUNNING',
                        'details': {'volume_id': 'opaque'}, 'authorized_at': stamp})
    store.event('usb', 'SUCCESS', details={'files': 0, 'version': f'2026-07-01_180500_{version}_usb_{job}'})
    monkeypatch.setattr(windows_storage, 'cached_volumes', lambda engine: [])
    sign_in(client, 'admin')
    data = client.get('/admin/backups/data').json()
    assert data['last_usb']['excel_at_kyiv'] == '01.07.2026 18:05'
    assert data['last_usb']['files'] == 0 and data['last_usb']['label'] is None
    assert data['last_usb']['outdated'] is False

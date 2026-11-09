"""Encrypted local artifacts only; no working database or real personal information."""
from dataclasses import replace
from datetime import datetime,UTC,timedelta
from pathlib import Path
from types import SimpleNamespace
import base64,json,os,tarfile,io
import pytest
from app.services.backups.config import BackupConfig
from app.services.backups.crypto import Keyring,private_file,private_dir,sha,canonical
from app.services.backups.store import Store
from app.services.backups.bundle import pack,open_bundle
from app.database.postgresql import REVISION

@pytest.fixture
def backup_config(tmp_path,monkeypatch):
    paths={name:tmp_path/name for name in ('documents','photos','backups','temporary','exports')}
    for path in paths.values():private_dir(path)
    for name,data in [('main-key.json',b'a'*32),('secret-key.json',b'b'*32)]:
        with private_file(tmp_path/name) as out:out.write(canonical({'current':'one','keys':{'one':base64.b64encode(data).decode()}}))
    config=BackupConfig(root=paths['backups'],secrets=tmp_path/'capsules',staging=tmp_path/'staging',key_file=tmp_path/'main-key.json',secrets_key_file=tmp_path/'secret-key.json',release='synthetic-release',tool_dir=os.environ.get('PROJECT2_TEST_PG_TOOLS','/tmp/project2-pg17-bin'))
    config.validate(paths);private_dir(config.staging)
    monkeypatch.setenv('STAFF_SIGNING_KEY','synthetic-signing-key-not-production-'+'x'*32)
    return config,SimpleNamespace(environment='testing',paths=paths)


def test_encryption_authenticates_large_stream_and_rejects_wrong_key_and_damage(backup_config,tmp_path):
    c,_=backup_config;ring=Keyring(c.key_file);wrong=Keyring(c.secrets_key_file);source=tmp_path/'plain';source.write_bytes(b'PRIVATE-PDF'*200000)
    encrypted=tmp_path/'copy.p2b';ring.encrypt(source,encrypted,limit=c.max_bytes)
    assert b'PRIVATE-PDF' not in encrypted.read_bytes()
    ring.decrypt(encrypted,tmp_path/'result',limit=c.max_bytes);assert sha(source)==sha(tmp_path/'result')
    with pytest.raises(ValueError):wrong.decrypt(encrypted,tmp_path/'wrong',limit=c.max_bytes)
    assert not (tmp_path/'wrong').exists()
    content=bytearray(encrypted.read_bytes());content[-20]^=1;encrypted.write_bytes(content)
    with pytest.raises(ValueError):ring.decrypt(encrypted,tmp_path/'bad',limit=c.max_bytes)
    assert not (tmp_path/'bad').exists()


def test_signed_job_catalog_journal_and_duplicate_requests(backup_config):
    c,_=backup_config;store=Store(c,Keyring(c.key_file))
    first=store.enqueue('create',1);second=store.enqueue('create',1)
    assert first['id']==second['id'] and len(store.events())==1
    path=c.root/'jobs'/(first['id']+'.json');content=json.loads(path.read_text());content['data']['actor_user_id']=999;path.write_text(json.dumps(content))
    with pytest.raises(ValueError,match='METADATA'):store.records('jobs')
    journal=c.root/'operations.json';journal.write_text(journal.read_text().replace('QUEUED','SUCCESS'))
    with pytest.raises(ValueError,match='JOURNAL'):store.events()


def test_schedule_meets_hourly_frequency_and_keeps_daily_full_distinct(backup_config,monkeypatch):
    from app.services.backups import store as module
    c,_=backup_config;store=Store(c,Keyring(c.key_file));clock=datetime(2026,11,8,3,tzinfo=UTC);monkeypatch.setattr(module,'now',lambda:clock)
    assert store.due([])[1]=='full'
    records=[{'snapshot_at':(clock-timedelta(minutes=10)).isoformat(),'kind':'full','integrity':'VERIFIED'}]
    due,kind=store.due(records);assert kind=='checkpoint' and due==clock+timedelta(minutes=20)
    with pytest.raises(ValueError):replace(c,interval_minutes=61).validate(backup_config[1].paths)


def test_config_rejects_overlapping_staging_and_keys(backup_config):
    c,s=backup_config
    public=Path(__file__).resolve().parents[1]/'app'/'static'
    for changed in [replace(c,staging=s.paths['documents']),replace(c,key_file=c.root/'key.json'),replace(c,external=c.root/'external',external_marker='test-volume'),replace(c,staging=public/'insecure-backup')]:
        with pytest.raises(ValueError):changed.validate(s.paths)


def test_malicious_tar_member_is_not_extracted_even_with_valid_encryption(backup_config,tmp_path):
    c,_=backup_config;ring=Keyring(c.key_file);secret=Keyring(c.secrets_key_file);raw=tmp_path/'malicious.tar'
    with tarfile.open(raw,'w') as out:
        info=tarfile.TarInfo('../../outside');info.size=3;out.addfile(info,io.BytesIO(b'bad'))
    secret_json=tmp_path/'values';secret_json.write_text('{}');capsule=tmp_path/'secret.p2s';secret.encrypt(secret_json,capsule,limit=1024)
    archive=tmp_path/'copy.p2b';ring.encrypt(raw,archive,limit=c.max_bytes)
    with pytest.raises(ValueError,match='ARCHIVE'):
        with open_bundle(c,ring,secret,archive,capsule):pass
    assert not (c.staging.parent/'outside').exists()


def test_quota_failure_does_not_replace_any_previous_archive(backup_config,tmp_path):
    c,_=backup_config;source=tmp_path/'source';source.write_bytes(b'x'*10000);ring=Keyring(c.key_file)
    old=c.root/'existing-old.dump';old.write_bytes(b'untouched')
    with pytest.raises(ValueError,match='QUOTA'):ring.encrypt(source,tmp_path/'too-large',limit=100)
    assert old.read_bytes()==b'untouched' and not (tmp_path/'too-large').exists()


def test_encryption_collision_never_deletes_existing_copy(backup_config,tmp_path):
    c,_=backup_config;ring=Keyring(c.key_file);source=tmp_path/'plain';source.write_bytes(b'new');target=tmp_path/'old';target.write_bytes(b'keep')
    with pytest.raises(FileExistsError):ring.encrypt(source,target,limit=10000)
    assert target.read_bytes()==b'keep'
    from app.services.backups.engine import publish
    partial=tmp_path/'.published.partial';partial.write_bytes(b'preexisting')
    with pytest.raises(FileExistsError):publish(source,tmp_path/'published')
    assert partial.read_bytes()==b'preexisting'
    with pytest.raises(ValueError):ring.decrypt(source,target,limit=10000)
    assert target.read_bytes()==b'keep'


def test_journal_truncation_is_detected_by_authenticated_envelope(backup_config):
    c,_=backup_config;store=Store(c,Keyring(c.key_file));store.event('first','SUCCESS');store.event('second','FAILED',code='BACKUP_FAILED')
    path=c.root/'operations.json';data=json.loads(path.read_text());data['data']['events'].pop();path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='JOURNAL'):store.events()


def test_key_rotation_keeps_old_archives_and_audit_verifiable(backup_config,tmp_path):
    c,_=backup_config;old=Keyring(c.key_file);store=Store(c,old);store.event('old','SUCCESS')
    plain=tmp_path/'plain';plain.write_bytes(b'synthetic secret');archive=tmp_path/'old.p2b';old.encrypt(plain,archive,limit=10000)
    payload=json.loads(c.key_file.read_text());payload['current']='two';payload['keys']['two']=base64.b64encode(b'c'*32).decode()
    c.key_file.write_bytes(canonical(payload));rotated=Keyring(c.key_file)
    rotated.decrypt(archive,tmp_path/'recovered',limit=10000)
    updated=Store(c,rotated);updated.event('new','SUCCESS')
    assert [e['operation'] for e in updated.events()]==['old','new']
    assert (tmp_path/'recovered').read_bytes()==plain.read_bytes()

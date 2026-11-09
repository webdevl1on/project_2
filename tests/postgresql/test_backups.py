"""Actual pg_dump/pg_restore and consistency, only disposable CI databases/files."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,UTC,timedelta
from dataclasses import replace
from pathlib import Path
import json,time,uuid
import pytest
from sqlalchemy import create_engine,text,select
from sqlalchemy.orm import Session
from app.models import User,Person,PersonName,PersonDocument,AccessRule
from app.models.mfa import TotpFactor
from app.models import UserSession
from app.services import accounts,documents,document_files
from app.services.backups.engine import BackupEngine
from app.services.backups import restore
from app.services.backups.bundle import open_bundle
from app.database.postgresql import require_postgresql_schema
from app.database.backup_maintenance import protect_write,MaintenanceUnavailable
from tests.test_backups import backup_config
from tests.mfa_helpers import login

PASSWORD='synthetic-recovery-password'

@pytest.fixture
def prepared(pg_factory,backup_config):
    config,settings=backup_config;engine=pg_factory.kw['bind']
    with pg_factory() as db:
        master=accounts.create_user(db,'backup-master','Synthetic Master',PASSWORD,'admin');accounts.promote_master(db,master,PASSWORD,confirmed=True)
        admin=accounts.create_user(db,'backup-admin','Synthetic Admin',PASSWORD,'admin',actor_id=master)
        user=accounts.create_user(db,'backup-user','Synthetic User',PASSWORD,'user',actor_id=admin)
        p=Person(tax_number='0000000001');db.add(p);db.flush();db.add(PersonName(person_id=p.person_id,surname='Синтетичний',name='Тест'))
        db.add(AccessRule(user_id=user,scope_type='person',person_id=p.person_id,category='basic',action='read',effect='ALLOW',created_by=master));db.commit()
        documents.seed_types(db);db.commit();doc=documents.save(db,admin,p.person_id,'other',{'number':'TEST-RESTORE'})
        from app.services.document_storage import DocumentStorage
        fid=document_files.attach(db,admin,p.person_id,doc,db.get(PersonDocument,doc).revision,b'%PDF-1.7 synthetic protected copy','synthetic.pdf','front',storage=DocumentStorage(settings.paths['documents']))
        token,_=login(db,'backup-master',PASSWORD)
        capsule_code=db.scalar(select(TotpFactor.ciphertext));pid=p.person_id
    (settings.paths['photos']/'test-photo.png').write_bytes(b'\x89PNG\r\n\x1a\nsynthetic-photo')
    backup=BackupEngine(engine,settings,config)
    return backup,pg_factory,{'master':master,'admin':admin,'user':user,'person':pid,'file':fid,'token':token,'ciphertext':capsule_code}

@pytest.fixture
def target(prepared):
    backup,_,_=prepared;database='project2_restore_'+uuid.uuid4().hex[:16];url=backup.db_engine.url.set(database=database)
    admin=create_engine(backup.db_engine.url,isolation_level='AUTOCOMMIT')
    with admin.connect() as db:db.execute(text('CREATE DATABASE "'+database+'"'))
    try:yield url
    finally:
        with admin.connect() as db:db.execute(text('DROP DATABASE "'+database+'" WITH (FORCE)'))
        admin.dispose()


def test_real_complete_backup_and_isolated_restore_preserve_accounts_acl_mfa_documents(prepared,target,tmp_path):
    backup,factory,ids=prepared
    first=backup.create(actor=ids['master']);second=backup.create(kind='checkpoint',actor=ids['master'])
    assert first['integrity']==second['integrity']=='VERIFIED' and first['id']!=second['id']
    plan=restore.plan(backup,first['id'],target.render_as_string(hide_password=False),actor=ids['master'],reason='Ізольоване випробування')
    report=restore.apply(backup,plan['id'],target.render_as_string(hide_password=False),tmp_path/'recovered',actor=ids['master'],confirmed=True)
    recovered=create_engine(target,connect_args={'options':'-c search_path='+report['schema']+',public'})
    try:
        require_postgresql_schema(recovered)
        with Session(recovered) as db:
            assert db.get(User,ids['master']).role=='master' and db.get(User,ids['user']).role=='user'
            assert db.scalar(select(TotpFactor.ciphertext))==ids['ciphertext']
            assert db.scalar(select(AccessRule)).effect=='ALLOW'
            assert not db.scalars(select(UserSession)).all()
            from app.models import DocumentFile
            f=db.get(DocumentFile,ids['file']);assert (tmp_path/'recovered/documents'/f.storage_key).read_bytes().startswith(b'%PDF')
        assert (tmp_path/'recovered/photos/test-photo.png').read_bytes().endswith(b'synthetic-photo')
        with factory() as db:assert accounts.authenticate(db,ids['token'])[0].id==ids['master']
        assert 'PROJECT2_MFA_KEYS' not in (tmp_path/'recovered/recovery.json').read_text()
        print('RECOVERY_BENCHMARK',json.dumps({'backup_seconds':first['duration_seconds'],'freeze_seconds':first['freeze_seconds'],'restore_seconds':report['restore_seconds'],'counts':report['counts']}))
    finally:recovered.dispose()


def test_exported_snapshot_matches_files_while_concurrent_writes_resume(prepared,monkeypatch):
    backup,factory,ids=prepared
    from app.repositories.backup_repository import BackupRepository
    original=BackupRepository.tool;created=[]
    def concurrent(config,name,args,env,**kw):
        if name=='pg_dump':
            with factory() as db:
                p=Person();db.add(p);db.commit();created.append(p.person_id)
        return original(config,name,args,env,**kw)
    monkeypatch.setattr(BackupRepository,'tool',concurrent)
    record=backup.create()
    archive,capsule=backup.locations(record['id'])
    with open_bundle(backup.config,backup.ring,backup.secret_ring,archive,capsule) as (manifest,_,__):assert manifest['counts']['persons']==1
    with factory() as db:assert db.get(Person,created[0]) is not None


def test_snapshot_gate_blocks_writes_not_reads_and_duplicate_backup(prepared):
    backup,factory,_=prepared
    from app.repositories.backup_repository import BackupRepository as Repo
    with Repo.lock(backup.db_engine) as lock:
        with ThreadPoolExecutor() as pool:
            def attempt():
                with pytest.raises(ValueError,match='ALREADY_RUNNING'):
                    with Repo.lock(backup.db_engine):pass
            pool.submit(attempt).result(timeout=10)
        with Repo.freeze(lock):
            with factory() as db:
                assert db.scalar(select(Person.person_id))
                with pytest.raises(MaintenanceUnavailable):protect_write(db)
                db.rollback()
    with factory() as db:p=Person();db.add(p);db.commit()


def test_missing_file_failed_backup_and_corruption_keep_previous_point(prepared,target,tmp_path):
    backup,factory,ids=prepared;record=backup.create();archive,capsule=backup.locations(record['id']);original=archive.read_bytes()
    with factory() as db:
        from app.models import DocumentFile
        path=backup.settings.paths['documents']/db.get(DocumentFile,ids['file']).storage_key
    content=path.read_bytes();path.unlink()
    with pytest.raises(ValueError):backup.create()
    assert archive.read_bytes()==original and backup.store.status()['last_failure']
    path.write_bytes(content);damaged=bytearray(original);damaged[-30]^=1;archive.write_bytes(damaged)
    with pytest.raises(ValueError):restore.plan(backup,record['id'],str(target),actor=ids['master'],reason='Перевірка пошкодження')
    assert backup.store.read('catalog',record['id'])['integrity']=='VERIFIED' # plan never trusts or changes catalog status


def test_failed_restore_never_touches_source_or_publishes_files(prepared,target,tmp_path,monkeypatch):
    backup,factory,ids=prepared;record=backup.create();plan=restore.plan(backup,record['id'],str(target),actor=ids['master'],reason='Тест відмови')
    public=Path(__file__).resolve().parents[2]/'app'/'static'/'insecure-recovery'
    with pytest.raises(ValueError,match='OUTPUT_OVERLAPS_SOURCE'):
        restore.apply(backup,plan['id'],str(target),public,actor=ids['master'],confirmed=True)
    def fail(*_):raise ValueError('synthetic postcheck failure')
    monkeypatch.setattr(restore,'require_postgresql_schema',fail)
    with pytest.raises(ValueError,match='QUARANTINED'):restore.apply(backup,plan['id'],str(target),tmp_path/'never-published',actor=ids['master'],confirmed=True)
    assert not (tmp_path/'never-published').exists()
    with factory() as db:assert db.get(Person,ids['person']) and accounts.authenticate(db,ids['token'])


def test_external_copy_verifies_and_retention_is_opt_in(prepared,tmp_path):
    backup,_,_=prepared;external=tmp_path/'external';external.mkdir();(external/'.project2-backup-volume').write_text('synthetic-volume')
    backup.config=replace(backup.config,external=external,external_marker='synthetic-volume')
    backup.store.config=backup.config
    record=backup.create();assert record['external']=='VERIFIED'
    assert backup.verify(record['id'],external=True)['id']==record['id']
    (external/'.project2-backup-volume').unlink()
    with pytest.raises(ValueError,match='EXTERNAL_FAILED'):backup.create()
    assert backup.locations(record['id'])[0].exists()


def test_scheduled_drill_needs_scoped_master_permit_and_restores_real_database(prepared,tmp_path,monkeypatch):
    from app.services.backups import drills
    backup,_,ids=prepared;backup.create();backup.config=replace(backup.config,drill_root=tmp_path/'drills');backup.store.config=backup.config
    assert drills.maybe_run(backup) is None
    monkeypatch.setenv('PROJECT2_BACKUP_DRILL_DATABASE_URL',backup.db_engine.url.render_as_string(hide_password=False))
    drills.approve(backup,ids['master'],'PROJECT2_BACKUP_DRILL_DATABASE_URL','Регулярний синтетичний тест',1,True)
    report=drills.maybe_run(backup);assert report['state']=='VERIFIED_ISOLATED'
    assert drills.maybe_run(backup) is None
    assert any(e['operation']=='drill' and e['result']=='SUCCESS' for e in backup.store.events())
    assert not list(backup.config.drill_root.iterdir())


def test_retention_does_not_remove_good_older_copy_if_newer_is_damaged(prepared,monkeypatch):
    from app.services.backups import engine as module
    backup,_,_=prepared
    rows=[backup.create() for _ in range(3)];old=backup.locations(rows[0]['id'])[0];new=backup.locations(rows[-1]['id'])[0]
    changed=bytearray(new.read_bytes());changed[-25]^=1;new.write_bytes(changed)
    from datetime import timedelta
    monkeypatch.setattr(module,'now',lambda:datetime.now(UTC)+timedelta(days=100))
    backup.prune();assert old.exists() and backup.verify(rows[0]['id'])['id']==rows[0]['id']


def test_worker_jobs_survive_restart_recheck_identity_and_do_not_invent_actor(prepared):
    backup,factory,ids=prepared
    job=backup.store.enqueue('create',ids['master'])
    restarted=BackupEngine(backup.db_engine,backup.settings,backup.config);assert restarted.run_once()
    done=backup.store.read('jobs',job['id']);assert done['state']=='SUCCESS'
    assert any(e['operation']=='backup' and e['result']=='SUCCESS' and e['actor_user_id']==ids['master'] for e in backup.store.events())
    job=backup.store.enqueue('verify',ids['user'],done['backup_id']);assert not restarted.run_once()
    assert backup.store.read('jobs',job['id'])['state']=='FAILED'


def test_version_mismatch_and_wrong_capsule_key_refuse_restore_without_touching_target(prepared,target,tmp_path):
    backup,_,ids=prepared;record=backup.create()
    mismatched=BackupEngine(backup.db_engine,backup.settings,replace(backup.config,release='different-release'))
    with pytest.raises(ValueError,match='VERSION'):restore.plan(mismatched,record['id'],str(target),actor=ids['master'],reason='Перевірка версії')
    backup.secret_ring=backup.ring
    with pytest.raises(ValueError,match='AUTHENTICATION'):restore.plan(backup,record['id'],str(target),actor=ids['master'],reason='Перевірка ключа')
    with create_engine(target).connect() as db:assert db.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')"))==0


def test_chromium_real_backup_queue_and_worker(prepared,monkeypatch,tmp_path):
    import os,subprocess,threading,socket
    import uvicorn
    from dataclasses import asdict
    from app.main import app
    from app.database.db import get_db
    from app.services.backups import commands
    backup,factory,ids=prepared;monkeypatch.setattr(commands,'settings',backup.settings)
    config=asdict(backup.config)
    for k,v in list(config.items()):
        if isinstance(v,Path):config[k]=str(v)
    config.pop('root');filename=tmp_path/'config.json';filename.write_text(json.dumps(config));monkeypatch.setenv('PROJECT2_BACKUP_CONFIG',str(filename));monkeypatch.setenv('PROJECT2_AUTH_ALLOW_LOCAL_HTTP','1')
    previous=dict(app.dependency_overrides)
    def override():
        with factory() as db:yield db
    app.dependency_overrides[get_db]=override
    server_socket=socket.socket();server_socket.bind(('127.0.0.1',0));server_socket.listen(128);port=server_socket.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'));thread=threading.Thread(target=lambda:server.run(sockets=[server_socket]),daemon=True);thread.start()
    environment={**os.environ,'PROJECT2_BROWSER_BACKUP':json.dumps({'base':f'http://localhost:{port}','token':ids['token']})}
    process=subprocess.Popen(['node','tests/browser/backups_live.cjs'],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+120
        while process.poll() is None and time.monotonic()<deadline:
            if any(j['state']=='QUEUED' for j in backup.store.records('jobs')):assert backup.run_once()
            time.sleep(.1)
        if process.poll() is None:process.kill()
        output,error=process.communicate(timeout=10)
        assert process.returncode==0,error
        assert output.count('PASS backup UI:')==3
        print(output)
    finally:
        if process.poll() is None:process.kill();process.wait()
        server.should_exit=True;thread.join(timeout=10);server_socket.close()
        app.dependency_overrides.clear();app.dependency_overrides.update(previous)


def test_disaster_recovery_requires_real_restored_master_and_mfa(prepared,target,tmp_path,monkeypatch):
    from app.services.backup import recovered_master
    from app.services import mfa
    backup,factory,ids=prepared
    with factory() as db:code=mfa.backup_generate(db,ids['master'])[0]
    record=backup.create()
    proposal=restore.plan(backup,record['id'],str(target),actor=None,reason='Локальна перевірка втрати вихідної БД')
    # A real unused recovery code issued by the existing MFA service.
    answers=iter(['backup-master','backup']);secrets=iter([PASSWORD,code])
    monkeypatch.setattr('builtins.input',lambda *_:next(answers));monkeypatch.setattr('getpass.getpass',lambda *_:next(secrets))
    report=restore.apply(backup,proposal['id'],str(target),tmp_path/'disaster-recovered',actor=None,confirmed=True,authorize=recovered_master)
    assert report['confirmed_master_id']==ids['master']
    assert any(e['operation']=='restore' and e['result']=='SUCCESS' and e['actor_user_id']==ids['master'] for e in backup.store.events())
    with factory() as db:assert accounts.authenticate(db,ids['token'])[0].id==ids['master']


def test_recovery_benchmark_synthetic_5000_people_and_24mib_files(prepared,target,tmp_path):
    import os
    from app.services.document_storage import DocumentStorage
    backup,factory,ids=prepared
    with factory() as db:
        people=[Person() for _ in range(5000)];db.add_all(people);db.flush()
        db.add_all(PersonName(person_id=p.person_id,surname='Синтетичний',name='Тест') for p in people);db.commit()
        doc=db.scalar(select(PersonDocument))
        for index in range(3):
            data=b'%PDF-1.7\n'+os.urandom(8*1024*1024-9)
            document_files.attach(db,ids['admin'],ids['person'],doc.id,db.get(PersonDocument,doc.id).revision,data,f'benchmark-{index}.pdf','page',storage=DocumentStorage(backup.settings.paths['documents']))
    record=backup.create();proposal=restore.plan(backup,record['id'],str(target),actor=ids['master'],reason='Вимірювання на синтетичному обсязі')
    report=restore.apply(backup,proposal['id'],str(target),tmp_path/'benchmark-recovered',actor=ids['master'],confirmed=True)
    assert report['counts']['persons']==5001 and report['counts']['document_files']==4
    print('VOLUME_BENCHMARK',json.dumps({'people':5001,'document_bytes':24*1024*1024,'archive_bytes':record['size'],'backup_seconds':record['duration_seconds'],'freeze_seconds':record['freeze_seconds'],'restore_seconds':report['restore_seconds']}))


def test_target_lease_serializes_restore_from_different_output_roots(prepared,target,tmp_path,monkeypatch):
    from threading import Event
    backup,_,ids=prepared;record=backup.create()
    import shutil
    other=BackupEngine(backup.db_engine,backup.settings,replace(backup.config,root=tmp_path/'other-backups'))
    other.store.initialize()
    shutil.copyfile(backup.locations(record['id'])[0],other.locations(record['id'])[0])
    proposals=[restore.plan(service,record['id'],str(target),actor=ids['master'],reason='Перевірка конкуренції') for service in (backup,other)]
    entered=Event();release=Event();original=restore.require_postgresql_schema
    def pause(engine):
        entered.set();assert release.wait(20);return original(engine)
    monkeypatch.setattr(restore,'require_postgresql_schema',pause)
    with ThreadPoolExecutor() as pool:
        first=pool.submit(restore.apply,backup,proposals[0]['id'],str(target),tmp_path/'first'/'recovered',actor=ids['master'],confirmed=True)
        try:
            assert entered.wait(20)
            with pytest.raises(ValueError,match='QUARANTINED'):
                restore.apply(other,proposals[1]['id'],str(target),tmp_path/'second'/'recovered',actor=ids['master'],confirmed=True)
        finally:release.set()
        assert first.result(timeout=20)['state']=='VERIFIED_ISOLATED'
    with pytest.raises(ValueError,match='INVALID_OR_EXPIRED'):
        restore.apply(backup,proposals[0]['id'],str(target),tmp_path/'third',actor=ids['master'],confirmed=True)
    assert not (tmp_path/'second'/'recovered').exists()

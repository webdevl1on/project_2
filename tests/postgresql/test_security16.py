"""Actual PG17 dump/drill/emergency snapshot, only disposable project2_ci schemas."""
from dataclasses import replace,asdict
from datetime import datetime,UTC,date
from pathlib import Path
import json,os,time
import pytest
from sqlalchemy import select,text,func
from sqlalchemy.orm import Session
from app.models import Person,PersonName,User,SubjectAudit,DocumentFile,PersonDocument,UserSession
from app.services import accounts
from app.services.backups import drills,emergency
from app.services.backups.engine import BackupEngine
from app.services.backups.crypto import sha,private_dir
from app.repositories.backup_repository import BackupRepository as Repo
from tests.postgresql.test_backups import prepared,approve_worker_drill,PASSWORD,target
from tests.test_backups import backup_config


def test_hourly_worker_dump_verify_real_drill_and_restart_reuse_same_copy(prepared,tmp_path,monkeypatch):
    backup,factory,ids=prepared;approve_worker_drill(backup,ids,tmp_path,monkeypatch)
    source=backup.db_engine
    with source.connect() as db:before=Repo.counts(db)
    original=drills.restore.apply;calls=[]
    def fail_once(*args,**kwargs):
        calls.append(1)
        if len(calls)==1:raise ValueError('synthetic restore failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(drills.restore,'apply',fail_once)
    job=backup.store.enqueue('create',ids['admin'])
    assert not backup.run_once();first=backup.store.read('jobs',job['id']);assert first['state']=='QUEUED'
    record=backup.store.read('catalog',first['backup_id']);assert record['integrity']=='VERIFIED' and record['drill']=='FAILED'
    original_hash=sha(backup.locations(record['id'])[0])
    restarted=BackupEngine(source,backup.settings,backup.config);assert restarted.run_once()
    second=backup.store.read('jobs',job['id']);assert second['backup_id']==record['id'] and second['attempts']==2 and second['state']=='SUCCESS'
    assert len(backup.store.records('catalog'))==1 and sha(backup.locations(record['id'])[0])==original_hash
    assert backup.store.status()['last_success']['id']==record['id']
    automation=[e for e in backup.store.events() if e['operation']=='drill' and e['result']=='SUCCESS']
    assert automation[-1]['actor_user_id'] is None and automation[-1]['details']['approved_by_user_id']==ids['master']
    assert automation[-1]['details']['initiated_by_user_id']==ids['admin']
    with source.connect() as db:assert before==Repo.counts(db)
    assert not list(backup.config.drill_root.iterdir())


def test_real_emergency_consistent_versions_and_source_is_unchanged(prepared,tmp_path):
    backup,factory,ids=prepared
    backup.config=replace(backup.config,emergency_root=tmp_path/'readable');backup.store.config=backup.config
    private_dir(backup.config.emergency_root)
    with factory() as db:
        p=db.get(Person,ids['person']);p.birth_month=3;p.birth_year=1990;db.commit()
        counts=Repo.counts(db.connection())
    first=emergency.generate(backup,actor=ids['admin']);second=emergency.generate(backup,actor=ids['admin'])
    records=backup.store.records('emergency');assert first['id']!=second['id'] and len(records)==2
    for record in records:
        assert 'files' not in record and record['file_count']==2
        record=emergency.load_manifest(backup,record)
        emergency.verify(backup,record)
        assert len(record['books'])==3 and record['files'] and record['revision'].startswith('0011_')
        assert (backup.config.emergency_root/record['path']/'manifest.json').exists()
    from openpyxl import load_workbook
    book=load_workbook(backup.config.emergency_root/records[0]['path']/emergency.BOOKS[0])
    headers=[c.value for c in book['Анкетні дані'][1]];values=[c.value for c in book['Анкетні дані'][2]]
    assert values[headers.index('Дата народження')]=='_.03.1990' and values[headers.index('person_id')]==ids['person']
    assert len(list((backup.config.emergency_root/'Документи').rglob('*.pdf')))==1
    with factory() as db:assert counts==Repo.counts(db.connection())


def test_new_audit_migration_has_no_backfill_and_pg_append_only_guards(pg_factory):
    from app.models import AccountAudit
    from sqlalchemy.exc import DBAPIError
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(SubjectAudit))==0
        assert db.scalar(select(func.count()).select_from(AccountAudit))==0
        p=Person();db.add(p);db.commit()
        assert db.scalar(select(func.count()).select_from(SubjectAudit))==1
        for statement in ('UPDATE subject_audit SET operation=\'delete\'','DELETE FROM subject_audit'):
            with pytest.raises(DBAPIError):db.execute(text(statement));db.commit()
            db.rollback()

def test_subject_audit_after_uses_committed_values_when_an_editor_loaded_stale_data(prepared):
    backup,factory,ids=prepared
    with factory() as older,factory() as current:
        stale=older.get(Person,ids['person'])
        person=current.get(Person,ids['person']);person.personal_number='committed-by-first-editor';current.commit()
        stale.birth_year=1990;older.commit()
        audit=older.scalar(select(SubjectAudit).where(SubjectAudit.object_type=='persons',SubjectAudit.object_id==ids['person']).order_by(SubjectAudit.id.desc()))
        assert audit.before['personal_number']==audit.after['personal_number']=='committed-by-first-editor'
        assert audit.before['birth_year'] is None and audit.after['birth_year']==1990

def test_full_backup_preserves_segmented_operational_history(prepared,target,tmp_path):
    from app.services.backups import restore
    from app.services.backups.store import Store
    import shutil
    backup,_,ids=prepared
    for i in range(501):backup.store.event('synthetic_history','SUCCESS',details={'number':i})
    record=backup.create(actor=ids['admin'])
    url=target.render_as_string(hide_password=False)
    plan=restore.plan(backup,record['id'],url,actor=ids['master'],reason='Ізольована перевірка сегментів журналу')
    output=tmp_path/'recovered';restore.apply(backup,plan['id'],url,output,actor=ids['master'],confirmed=True)
    root=tmp_path/'journal-reader';private_dir(root)
    shutil.copyfile(output/'prior-operations.json',root/'operations.json');shutil.copytree(output/'prior-operations',root/'operations')
    recovered=Store(replace(backup.config,root=root),backup.ring)
    assert len([e for e in recovered.events() if e['operation']=='synthetic_history'])==501


def test_emergency_scheduled_requires_scoped_master_without_granting_subject_reads(prepared,tmp_path,monkeypatch):
    backup,factory,ids=prepared;backup.config=replace(backup.config,emergency_root=tmp_path/'readable');backup.store.config=backup.config
    with pytest.raises(ValueError,match='APPROVAL'):emergency.generate(backup)

    from app.services import access
    with factory() as db:
        assert not access.Access(db,ids['master']).allowed('medical',person_id=ids['person'])
    emergency.approve(backup,ids['master'],'Автоматичний фіксований експорт до відкликання',0,True)
    assert emergency.generate(backup)['files']==2 # document and unassigned photo
    with factory() as db:
        assert not access.Access(db,ids['master']).allowed('medical',person_id=ids['person'])
    permit=backup.ring.read(backup.config.root/'emergency-permit.json');permit['active']=False;backup.ring.save(backup.config.root/'emergency-permit.json',permit)
    with pytest.raises(ValueError,match='APPROVAL'):emergency.generate(backup)


def test_chromium_emergency_usb_audit_and_fresh_mfa(prepared,tmp_path,monkeypatch):
    import subprocess,threading,socket
    import uvicorn
    from datetime import timedelta
    from tests.mfa_helpers import login
    from app.main import app
    from app.database.db import get_db
    from app.services.backups import commands,windows_storage
    backup,factory,ids=prepared
    backup.config=replace(backup.config,emergency_root=tmp_path/'readable',usb_volume_ids=('synthetic-volume',));backup.store.config=backup.config
    private_dir(backup.config.emergency_root);root=tmp_path/'usb';private_dir(root/'Project_2')
    volume={'volume_id':'synthetic-volume','disk_id':'test','serial':'test','root':'X:\\','label':'Синтетичний USB','size':10**12,'free':10**12,'eligible':True}
    volume['id']=windows_storage.identity(volume)
    backup.ring.save(backup.config.root/'devices.json',{'at':datetime.now(UTC).isoformat(),'volumes':[volume],'code':None})
    monkeypatch.setattr(windows_storage,'select_volume',lambda b,v:(volume,root) if v==volume['id'] else (_ for _ in ()).throw(ValueError('USB_VOLUME_CHANGED_OR_NOT_ALLOWED')))
    monkeypatch.setattr(windows_storage,'secure_usb_root',lambda *_:root/'Project_2')
    monkeypatch.setattr(commands,'settings',backup.settings)
    with factory() as db:
        admin,_=login(db,'backup-admin',PASSWORD)
        person=db.get(Person,ids['person']);person.personal_number='SECRET-SYNTHETIC-PERSON';db.commit()
        from app.services import audit
        assert audit.filtered(db,'subject',{'q':'SECRET-SYNTHETIC-PERSON'},user_id=ids['admin'])
    config={k:str(v) if isinstance(v,Path) else v for k,v in asdict(backup.config).items()};config.pop('root')
    filename=tmp_path/'config.json';filename.write_text(json.dumps(config));monkeypatch.setenv('PROJECT2_BACKUP_CONFIG',str(filename));monkeypatch.setenv('PROJECT2_AUTH_ALLOW_LOCAL_HTTP','1')
    previous=dict(app.dependency_overrides)
    def override():
        with factory() as db:yield db
    app.dependency_overrides[get_db]=override
    server_socket=socket.socket();server_socket.bind(('127.0.0.1',0));server_socket.listen(128);port=server_socket.getsockname()[1]
    server=uvicorn.Server(uvicorn.Config(app,log_level='error'));thread=threading.Thread(target=lambda:server.run(sockets=[server_socket]),daemon=True);thread.start()
    control=tmp_path/'control';control.mkdir()
    environment={**os.environ,'PROJECT2_BROWSER_SECURITY16':json.dumps({'base':f'http://localhost:{port}','admin':admin,'master':ids['token'],'volume':volume['id'],'control':str(control)})}
    process=subprocess.Popen(['node','tests/browser/security16_live.cjs'],env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    try:
        deadline=time.monotonic()+120
        while process.poll() is None and time.monotonic()<deadline:
            if any(j['state']=='QUEUED' for j in backup.store.records('jobs')):assert backup.run_once()
            if (control/'expire').exists() and not (control/'expired').exists():
                with factory() as db:
                    session=db.get(UserSession,accounts.digest_token(admin));session.created_at-=timedelta(minutes=10);session.mfa_verified_at-=timedelta(minutes=6);db.commit()
                (control/'expired').write_text('1')
            time.sleep(.1)
        if process.poll() is None:process.kill()
        output,error=process.communicate(timeout=10);assert process.returncode==0,error
        assert output.count('PASS Security 1.6 UI:')==5
        assert len(list((root/'Project_2').rglob('*.xlsx')))==3
        print(output)
    finally:
        if process.poll() is None:process.kill();process.wait()
        server.should_exit=True;thread.join(timeout=10);server_socket.close()
        app.dependency_overrides.clear();app.dependency_overrides.update(previous)

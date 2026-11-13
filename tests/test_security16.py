"""Synthetic-only emergency exports, safe IO, durable jobs and audit projections."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime,UTC,timedelta
from pathlib import Path
from types import SimpleNamespace
import json,hashlib,shutil
import pytest
from openpyxl import load_workbook,Workbook
from sqlalchemy import select,text,func,event
from sqlalchemy.exc import DBAPIError
from app.models import Person,PersonName,SubjectAudit,AccountAudit,DocumentFile,PersonDocument,User
from app.services import audit,accounts,documents,document_files,mfa
from app.services.backups import emergency,worker,windows_storage,usb,statistics
from app.services.backups.engine import BackupEngine
from app.services.backups.safe_files import SafeTree,safe_name,no_links
from app.services.backups.crypto import private_dir,sha
from tests.test_backups import backup_config
from tests.test_access_control import acl_store,rule,PASSWORD

@pytest.fixture
def archive(acl_store,backup_config,tmp_path):
    db,ids,factory=acl_store;config,settings=backup_config
    config=replace(config,emergency_root=tmp_path/'readable');private_dir(config.emergency_root)
    backup=BackupEngine(db.get_bind(),settings,config);backup.store.initialize()
    from app.services.document_storage import DocumentStorage
    pid=ids['people'][0];p=db.get(Person,pid);p.birth_year=1990;db.commit()
    doc=documents.save(db,ids['admin'],pid,'other',{'number':'EXAMPLE-1'})
    fid=document_files.attach(db,ids['admin'],pid,doc,db.get(PersonDocument,doc).revision,b'%PDF-1.7 synthetic copy','original.pdf','front',storage=DocumentStorage(settings.paths['documents']))
    return backup,db,ids,factory,doc,fid

def books(archive,tmp_path,name='one'):
    backup,db,*_=archive;target=tmp_path/name;private_dir(target)
    payload=SimpleNamespace()
    # Unit tests deliberately use only their isolated synthetic SQLite/files.
    payload=tmp_path/('payload-'+name);private_dir(payload)
    shutil.copytree(backup.settings.paths['documents'],payload/'documents');shutil.copytree(backup.settings.paths['photos'],payload/'photos')
    if backup.config.photo_index:shutil.copyfile(backup.config.photo_index,payload/'photo-index.json')
    files,counts=emergency.write_books(backup,db,target,payload)
    return target,files,counts

def records(book,sheet):
    rows=list(book[sheet].values);keys=rows[0]
    return [dict(zip(keys,r)) for r in rows[1:]]

def test_three_books_keep_ids_partial_dates_history_and_no_secrets(archive,tmp_path):
    backup,db,ids,_,doc,fid=archive
    target,files,counts=books(archive,tmp_path)
    assert sorted(p.name for p in target.iterdir())==sorted(emergency.BOOKS)
    book=load_workbook(target/emergency.BOOKS[0]);p=records(book,'Анкетні дані')[0]
    assert p['person_id']==ids['people'][0] and p['Повне ПІБ']=='Командир Тест' and p['Дата народження']=='_._.1990'
    for sheet in book:
        assert sheet.auto_filter.ref and sheet.freeze_panes=='C2'
        if sheet.title!='Анкетні дані':assert 'Дата народження' not in [c.value for c in sheet[1]]
    copies=records(book,'Копії документів');assert copies[0]['person_id']==ids['people'][0] and copies[0]['Повне ПІБ']=='Командир Тест'
    assert counts['person_assignments']==3 and counts['persons']==3
    text_=' '.join(str(c.value) for name in emergency.BOOKS for sheet in load_workbook(target/name) for row in sheet for c in row)
    for secret in (db.get(User,ids['admin']).password_hash,'ciphertext','csrf_token','token_hash','PROJECT2_MFA_KEYS'):
        assert secret not in text_
    assert load_workbook(target/emergency.BOOKS[2]).sheetnames==['Системний аудит','Аудит даних','Аудит резервування']
    assert files['files'][0]['source_id']=='document_file:'+str(fid)

def test_files_accumulate_without_duplicates_and_keep_removed_copies(archive,tmp_path):
    backup,db,ids,_,doc,fid=archive
    _,first,_=books(archive,tmp_path);old=first['files'][0];original=(backup.config.emergency_root/old['path']).read_bytes()
    row=db.get(DocumentFile,fid);row.is_removed=True;db.commit()
    name=db.scalar(select(PersonName).where(PersonName.person_id==ids['people'][0]));name.surname='Новий';db.commit()
    _,second,_=books(archive,tmp_path,'two');assert len(second['files'])==1
    from app.services.document_storage import DocumentStorage
    document_files.attach(db,ids['admin'],ids['people'][0],doc,db.get(PersonDocument,doc).revision,b'%PDF-1.7 replacement copy','new.pdf','front',storage=DocumentStorage(backup.settings.paths['documents']))
    _,third,_=books(archive,tmp_path,'three');assert len(third['files'])==2
    assert third['files'][1]['number']==2 and 'Новий' in third['files'][1]['path']
    assert (backup.config.emergency_root/old['path']).read_bytes()==original
    assert third['files'][0]['path']==old['path']

def test_same_names_dob_get_person_id_and_portraits_have_explicit_mapping(archive,tmp_path):
    backup,db,ids,*_=archive
    first=ids['people'][0];second=ids['people'][1]
    name=db.scalar(select(PersonName).where(PersonName.person_id==second));name.surname='Командир';p=db.get(Person,second);p.birth_year=1990;db.commit()
    (backup.settings.paths['photos']/'face.jpg').write_bytes(b'synthetic-photo');(backup.settings.paths['photos']/'unknown.jpg').write_bytes(b'unmapped-photo')
    index=tmp_path/'photo-index.json';index.write_text(json.dumps([{'person_id':second,'source_id':'portrait-1','relative_path':'face.jpg'}]))
    backup.config=replace(backup.config,photo_index=index)
    _,files,_=books(archive,tmp_path)
    doc=next(v for v in files['files'] if v['source_id'].startswith('document_file:'))
    face=next(v for v in files['files'] if v['source_id']=='photo:portrait-1')
    assert '(person_id '+str(first)+')' in doc['path'] and '(person_id '+str(second)+')' in face['path']
    assert 'Фото обличчя' in face['path'] and face['person_id']==second
    unknown=next(v for v in files['files'] if v['person_id'] is None);assert 'Нерозподілені фото' in unknown['path']

def test_missing_or_changed_source_is_not_silently_omitted(archive,tmp_path):
    backup,db,_,_,_,fid=archive
    (backup.settings.paths['documents']/db.get(DocumentFile,fid).storage_key).write_bytes(b'changed')
    with pytest.raises(ValueError,match='SOURCE_FILE'):books(archive,tmp_path)

def test_document_subtype_names_and_windows_name_collisions_keep_both_sources(archive,tmp_path):
    backup,db,ids,_,doc,fid=archive
    from app.models import DocumentDetails
    from app.services.document_storage import DocumentStorage
    db.get(DocumentDetails,doc).subtype='Витяг: наказ';db.commit()
    documents.archive(db,ids['admin'],ids['people'][0],doc,db.get(PersonDocument,doc).revision)
    second=documents.save(db,ids['admin'],ids['people'][0],'other',{'subtype':'Витяг? наказ','number':'second'})
    document_files.attach(db,ids['admin'],ids['people'][0],second,db.get(PersonDocument,second).revision,b'%PDF-1.7 second','second.pdf','front',storage=DocumentStorage(backup.settings.paths['documents']))
    _,manifest,_=books(archive,tmp_path)
    assert len(manifest['files'])==2 and all('Витяг_ наказ' in r['path'] for r in manifest['files'])
    assert all(r['number']==1 for r in manifest['files'])
    assert 'джерело' in manifest['files'][1]['path'] and len({r['path'] for r in manifest['files']})==2

def test_excel_splits_rows_and_long_cells_and_never_executes_formulas(tmp_path,monkeypatch):
    monkeypatch.setattr(emergency,'ROW_LIMIT',3);monkeypatch.setattr(emergency,'CELL_LIMIT',10)
    book=Workbook(write_only=True);sheet=emergency.Sheets(book,'Перевірка',[('person_id','person_id'),('text','Текст')])
    for value in ['=SUM(A1:A3)','+cmd','@formula','long text '*5]:sheet.add({'person_id':1,'text':value})
    sheet.finish();filename=tmp_path/'example.xlsx';book.save(filename)
    result=load_workbook(filename);assert len(result.sheetnames)>=3
    values=[]
    for part in result:
        assert part.max_row<=3 and part.auto_filter.ref
        for row in list(part)[1:]:assert row[1].data_type!='f';values.append(row[1].value)
    assert ''.join(v or '' for v in values).startswith('=SUM(A1:A3)+cmd@formula')

@pytest.mark.parametrize('relative',['../escape','a/../../b','/absolute','C:/drive','x:stream','a\\b','trailing.'])
def test_safe_tree_rejects_untrusted_paths(tmp_path,relative):
    root=tmp_path/'safe';root.mkdir();source=tmp_path/'source';source.write_bytes(b'ok')
    with pytest.raises(ValueError):SafeTree(root).copy(source,relative,sha(source))

def test_safe_tree_no_overwrite_no_symlink_and_retry_after_disk_error(tmp_path,monkeypatch):
    root=tmp_path/'safe';root.mkdir();source=tmp_path/'source';source.write_bytes(b'keep');tree=SafeTree(root)
    assert tree.copy(source,'folder/file.txt',sha(source)) and not tree.copy(source,'folder/file.txt',sha(source))
    source.write_bytes(b'different')
    with pytest.raises(ValueError,match='CONFLICT'):tree.copy(source,'folder/file.txt',sha(source))
    outside=tmp_path/'outside';outside.mkdir();(root/'jump').symlink_to(outside,target_is_directory=True)
    with pytest.raises((ValueError,OSError)):tree.copy(source,'jump/file',sha(source))
    original=shutil.copyfileobj
    def disk_error(*_):raise OSError('synthetic full/unplugged')
    monkeypatch.setattr(shutil,'copyfileobj',disk_error)
    with pytest.raises(OSError):tree.copy(source,'new/file',sha(source))
    assert not (root/'new/file').exists() and not list((root/'new').glob('*.partial'))
    monkeypatch.setattr(shutil,'copyfileobj',original);assert tree.copy(source,'new/file',sha(source))
    assert (root/'folder/file.txt').read_bytes()==b'keep'
    assert safe_name('CON')=='_CON' and ':' not in safe_name('a:b?')

def test_bitlocker_states_allowlist_and_volume_substitution(archive,monkeypatch):
    backup,*_=archive
    v={'volume_id':'\\\\?\\Volume{synthetic}\\','disk_id':'disk-1','serial':'one','bus':'USB','root':'X:\\','fs':'NTFS','free':10**9,'size':10**10,'protection':'On','lock':'Unlocked','encryption':'FullyEncrypted','percent':100}
    backup.config=replace(backup.config,usb_volume_ids=(v['volume_id'],))
    monkeypatch.setattr(windows_storage,'inspect_storage',lambda path=None:{'volumes':[v]})
    monkeypatch.setattr(windows_storage,'no_links',lambda p:p)
    identity=windows_storage.identity(v);assert windows_storage.volumes(backup)[0]['eligible']
    for change in ({'protection':'Off'},{'lock':'Locked'},{'percent':99},{'fs':'exFAT'}):
        current={**v,**change};monkeypatch.setattr(windows_storage,'inspect_storage',lambda path=None:{'volumes':[current]})
        with pytest.raises(ValueError,match='BITLOCKER'):windows_storage.select_volume(backup,identity)
    current={**v,'serial':'swapped'}
    with pytest.raises(ValueError,match='CHANGED'):windows_storage.select_volume(backup,identity)
    current={**v,'bus':'SATA'};assert windows_storage.volumes(backup)==[]

def test_ntfs_acl_rejects_broad_permissions_and_private_archive_is_not_static(archive):
    backup,*_=archive
    report={'worker_sid':'S-1-5-21-123','acl':{'protected':True,'rules':[{'sid':'S-1-1-0','type':'Allow','rights':1}]}}
    with pytest.raises(ValueError,match='ACL'):windows_storage.private_acl(report,())
    report['acl']['rules'][0]['sid']=report['worker_sid'];windows_storage.private_acl(report,())
    with pytest.raises(ValueError):replace(backup.config,emergency_root=Path(__file__).resolve().parents[1]/'app/static/private').validate(backup.settings.paths)

def test_win32_open_denies_reparse_and_never_shares_delete_or_replaces(backup_config,monkeypatch):
    import ctypes
    from ctypes import wintypes
    from app.services.backups import safe_files
    calls=[];closed=[];attributes=[0]
    class Kernel:
        def CreateFileW(self,*args):calls.append(args);return 123
        def GetFileInformationByHandleEx(self,handle,kind,pointer,size):
            ctypes.cast(pointer,ctypes.POINTER(wintypes.DWORD))[0]=attributes[0];return True
        def CloseHandle(self,handle):closed.append(handle)
    monkeypatch.setattr(safe_files,'winapi',lambda:(ctypes,wintypes,Kernel()))
    assert safe_files.win_open(Path('synthetic-directory'),directory=True)==123
    args=calls[-1];assert args[2]==1 and args[5]&0x00200000 and args[5]&0x02000000 # no FILE_SHARE_DELETE; open reparse itself
    assert safe_files.win_open(Path('synthetic-new-file'),write=True)==123
    args=calls[-1];assert args[4]==1 and args[1]&0x10000 # CREATE_NEW and DELETE access for handle rename
    attributes[0]=0x400
    with pytest.raises(ValueError,match='REPARSE'):safe_files.win_open(Path('synthetic-junction'),directory=True)
    assert closed==[123]

def test_usb_discovery_is_worker_cached_and_http_ids_are_revalidated(archive):
    backup,*_=archive
    v={'volume_id':'synthetic-id','id':'a'*64,'eligible':True,'root':'X:\\','label':'Synthetic','size':100,'free':80}
    backup.config=replace(backup.config,usb_volume_ids=(v['volume_id'],))
    backup.ring.save(backup.config.root/'devices.json',{'at':datetime.now(UTC).isoformat(),'volumes':[v],'code':None})
    windows_storage.check_request(backup,v['id'])
    with pytest.raises(ValueError):windows_storage.check_request(backup,'X:\\..\\private')
    assert not any('volume_id' in r for r in usb.available(backup))
    backup.ring.save(backup.config.root/'devices.json',{'at':(datetime.now(UTC)-timedelta(minutes=6)).isoformat(),'volumes':[v],'code':None})
    with pytest.raises(ValueError,match='DISCOVERY'):windows_storage.check_request(backup,v['id'])

def test_audit_filters_are_applied_after_acl_and_txt_cannot_search_forbidden_data(acl_store):
    db,ids,_=acl_store
    private=Person(birth_year=1990);db.add(private);db.flush();db.add(PersonName(person_id=private.person_id,surname='FORBIDDEN-SYNTHETIC',name='Name'));db.commit()
    assert audit.filtered(db,'subject',{'q':'FORBIDDEN-SYNTHETIC'},user_id=ids['master'])==[]
    assert 'FORBIDDEN-SYNTHETIC' not in ''.join(audit.text_export(audit.filtered(db,'subject',{},user_id=ids['master'])))
    rows=audit.filtered(db,'subject',{'q':'FORBIDDEN-SYNTHETIC','sort':'operation,-at'},user_id=ids['admin']);assert rows
    assert str(private.person_id) in ''.join(audit.text_export(rows))
    with pytest.raises(PermissionError):audit.filtered(db,'system',{},user_id=ids['user'])
    emergency.authorize_export(db,ids['master'])
    with pytest.raises(PermissionError):emergency.authorize_export(db,ids['user'])
    emergency.authorize_export(db,ids['admin'])
    with pytest.raises(ValueError):audit.filtered(db,'system',{'month':'invalid'},user_id=ids['admin'])

def test_new_subject_audit_is_atomic_append_only_and_has_verified_actor(acl_store):
    db,ids,factory=acl_store
    pid=ids['people'][0];person=db.get(Person,pid);person.personal_number='one';db.commit()
    row=db.scalar(select(SubjectAudit).where(SubjectAudit.object_type=='persons',SubjectAudit.object_id==pid).order_by(SubjectAudit.id.desc()))
    assert row.actor_user_id==ids['admin'] and row.after['personal_number']=='one'
    with pytest.raises(DBAPIError):db.execute(text('DELETE FROM subject_audit'));db.commit()
    db.rollback()
    with factory() as unknown:
        p=unknown.get(Person,pid);p.personal_number='two';unknown.commit()
        last=unknown.scalar(select(SubjectAudit).order_by(SubjectAudit.id.desc()));assert last.actor_user_id is None
    def fail(conn,cursor,statement,parameters,context,many):
        if 'INSERT INTO subject_audit' in statement:raise RuntimeError('synthetic audit failure')
    event.listen(db.get_bind(),'before_cursor_execute',fail)
    try:
        with pytest.raises(RuntimeError):person=db.get(Person,pid);person.personal_number='never saved';db.commit()
        db.rollback()
    finally:event.remove(db.get_bind(),'before_cursor_execute',fail)
    assert db.get(Person,pid).personal_number=='two'

def test_failed_login_and_mfa_are_logged_without_attempted_secret(acl_store):
    db,ids,_=acl_store
    for username in ('acl-admin','unknown-synthetic-login'):
        with pytest.raises(PermissionError):mfa.begin(db,username,'do-not-log-this-password')
    rows=list(db.scalars(select(AccountAudit).where(AccountAudit.operation=='login_failed')))
    assert len(rows)==2 and rows[-1].user_id is None
    data=' '.join(json.dumps(audit.normalized('account',r,{'actors':{},'assignments':{},'events':{},'medical_documents':set()})) for r in rows)
    assert 'do-not-log-this-password' not in data and 'unknown-synthetic-login' not in data
    from app.services.account_management import audit_page
    entries=audit_page(db,ids['admin'])['entries']
    failed=[r for r in entries if r['operation']=='Невдалий вхід']
    assert len(failed)==2 and all(r['actor']=='Автор невідомий' for r in failed)

def test_segmented_backup_audit_survives_restart_rotation_and_detects_removed_segment(backup_config):
    from app.services.backups.store import Store
    from app.services.backups.crypto import Keyring
    c,_=backup_config;store=Store(c,Keyring(c.key_file))
    for i in range(503):store.event('synthetic','SUCCESS',details={'number':i})
    assert len(store.events())==503 and len(list((c.root/'operations').glob('*.json')))==1
    assert len(Store(c,Keyring(c.key_file)).events())==503
    (c.root/'operations'/'000000000000.json').unlink()
    with pytest.raises(ValueError,match='JOURNAL'):store.events()

def fake_worker(backup,monkeypatch):
    @contextmanager
    def lock():yield
    monkeypatch.setattr(backup,'initialize',lambda:'synthetic-environment')
    monkeypatch.setattr(backup,'operation_lock',lock)

@pytest.mark.parametrize('utc_hour,day,expected',[(14,'2026-07-01',False),(15,'2026-07-01',True),(15,'2026-12-01',False),(16,'2026-12-01',True)])
def test_hourly_full_and_kyiv_18_schedule_dst_and_terminal_dedup(archive,monkeypatch,utc_hour,day,expected):
    backup,*_=archive;backup.config=replace(backup.config,emergency_enabled=True)
    at=datetime.fromisoformat(day).replace(hour=utc_hour,tzinfo=UTC);monkeypatch.setattr(worker,'now',lambda:at)
    worker.enqueue_due(backup);jobs=backup.store.records('jobs')
    creates=[j for j in jobs if j['operation']=='create'];assert len(creates)==2 and all(j['details']['kind']=='full' for j in creates)
    assert any(j['operation']=='emergency' for j in jobs)==expected
    for j in jobs:j['state']='FAILED';j['backup_id']='b'*32 if j['operation']=='create' else None;backup.store.save('jobs',j)
    worker.enqueue_due(backup);assert len(backup.store.records('jobs'))==len(jobs)
    monkeypatch.setattr(worker,'now',lambda:at+timedelta(hours=1));worker.enqueue_due(backup)
    assert len([j for j in backup.store.records('jobs') if j['operation']=='create'])==3

def test_worker_retry_once_persists_after_restart_and_alerts(archive,monkeypatch):
    backup,_,ids,*_=archive;fake_worker(backup,monkeypatch)
    job=backup.store.enqueue('statistics',ids['admin'])
    calls=[]
    def fail(*_):calls.append(1);raise ValueError('STORAGE_SYNTHETIC_FAILURE')
    monkeypatch.setattr(worker,'perform',fail)
    assert not worker.run_once(backup);first=backup.store.read('jobs',job['id']);assert first['state']=='QUEUED' and first['attempts']==1
    # A new Store reads the durable job; no in-process retry counter is trusted.
    from app.services.backups.store import Store
    backup.store=Store(backup.config,backup.ring)
    assert not worker.run_once(backup);final=backup.store.read('jobs',job['id']);assert final['state']=='FAILED' and final['attempts']==2 and len(calls)==2
    assert backup.ring.read(backup.config.root/'alert.json')['code']=='STORAGE_SYNTHETIC_FAILURE'

def test_interrupted_worker_resumes_only_one_remaining_attempt(archive,monkeypatch):
    backup,_,ids,*_=archive;fake_worker(backup,monkeypatch)
    job=backup.store.enqueue('statistics',ids['admin']);job.update(state='RUNNING',attempts=1);backup.store.save('jobs',job)
    monkeypatch.setattr(worker,'perform',lambda *_:{'ok':True})
    assert worker.run_once(backup)
    assert backup.store.read('jobs',job['id'])['attempts']==2

def test_power_return_catches_missed_18_job_without_forging_snapshot_date(archive,monkeypatch):
    backup,*_=archive;backup.config=replace(backup.config,emergency_enabled=True)
    monkeypatch.setattr(worker,'now',lambda:datetime(2026,11,12,14,tzinfo=UTC)) # 16:00 Kyiv
    worker.enqueue_due(backup)
    assert not any(j['operation']=='emergency' for j in backup.store.records('jobs'))
    monkeypatch.setattr(worker,'now',lambda:datetime(2026,11,13,5,tzinfo=UTC)) # next 07:00 Kyiv
    worker.enqueue_due(backup)
    assert [j['details']['slot'] for j in backup.store.records('jobs') if j['operation']=='emergency']==['2026-11-12']
    monkeypatch.setattr(worker,'now',lambda:datetime(2026,11,13,16,tzinfo=UTC))
    worker.enqueue_due(backup)
    assert {j['details']['slot'] for j in backup.store.records('jobs') if j['operation']=='emergency'}=={'2026-11-12','2026-11-13'}

def ready_archive(archive,tmp_path):
    backup,*_=archive;target,files,_=books(archive,tmp_path)
    tree=SafeTree(backup.config.emergency_root);manifest={'id':'a'*32,'path':'Excel/source-version','at':datetime.now(UTC).isoformat(),'day':'2026-11-12','ready':True,'books':{},'files':files['files']}
    for name in emergency.BOOKS:
        tree.copy(target/name,manifest['path']+'/'+name,sha(target/name));manifest['books'][name]={'sha256':sha(target/name),'size':(target/name).stat().st_size}
    private_dir(backup.config.root/'emergency');backup.store.save('emergency',manifest)
    return manifest

def mock_usb(backup,tmp_path,monkeypatch):
    root=tmp_path/'usb';private_dir(root/'Project_2')
    volume={'volume_id':'synthetic','serial':'same','disk_id':'same','free':10**12}
    monkeypatch.setattr(windows_storage,'select_volume',lambda *_:(volume,root))
    monkeypatch.setattr(windows_storage,'secure_usb_root',lambda *_:root/'Project_2')
    backup._worker_lock=object()
    return root/'Project_2',volume

def test_usb_versions_preserve_manual_excel_changes_conflict_and_safe_retry(archive,tmp_path,monkeypatch):
    backup,_,ids,*_=archive;ready_archive(archive,tmp_path);root,volume=mock_usb(backup,tmp_path,monkeypatch)
    first=usb.export(backup,'allowed-id',actor=ids['admin'],job_id='b'*32);assert first['files']==4
    edited=root/'Excel'/first['version']/emergency.BOOKS[0];edited.write_bytes(b'manually edited spreadsheet')
    with pytest.raises(ValueError,match='CONFLICT'):usb.export(backup,'allowed-id',actor=ids['admin'],job_id='b'*32)
    assert edited.read_bytes()==b'manually edited spreadsheet'
    second=usb.export(backup,'allowed-id',actor=ids['admin'],job_id='c'*32)
    assert second['version']!=first['version'] and edited.read_bytes()==b'manually edited spreadsheet'
    assert len(list((root/'Документи').rglob('*.pdf')))==1
    volume['free']=0
    with pytest.raises(ValueError,match='SPACE'):usb.export(backup,'allowed-id',actor=ids['admin'],job_id='d'*32)

def test_usb_unplug_leaves_no_ready_marker_and_retry_preserves_existing(archive,tmp_path,monkeypatch):
    backup,_,ids,*_=archive;ready_archive(archive,tmp_path);root,_=mock_usb(backup,tmp_path,monkeypatch)
    original=SafeTree.copy;calls=[]
    def unplug(self,source,path,digest):
        calls.append(path)
        if len(calls)==2:raise OSError('synthetic removed USB')
        return original(self,source,path,digest)
    monkeypatch.setattr(SafeTree,'copy',unplug)
    with pytest.raises(ValueError,match='USB_COPY_FAILED'):usb.export(backup,'allowed-id',actor=ids['admin'],job_id='e'*32)
    assert not list(root.rglob('manifest.json')) and len(list(root.rglob('*.xlsx')))==1
    monkeypatch.setattr(SafeTree,'copy',original)
    result=usb.export(backup,'allowed-id',actor=ids['admin'],job_id='e'*32)
    assert result['files']==3 and len(list(root.rglob('manifest.json')))==1

def test_usb_free_space_counts_only_missing_files(archive,tmp_path,monkeypatch):
    backup,db,ids,_,doc,_=archive
    from app.services.document_storage import DocumentStorage
    document_files.attach(db,ids['admin'],ids['people'][0],doc,db.get(PersonDocument,doc).revision,b'%PDF-1.7\n'+b'x'*(2*1024**2),'large.pdf','front',storage=DocumentStorage(backup.settings.paths['documents']))
    manifest=ready_archive(archive,tmp_path);root,volume=mock_usb(backup,tmp_path,monkeypatch)
    usb.export(backup,'allowed-id',actor=ids['admin'],job_id='b'*32)
    volume['free']=sum(v['size'] for v in manifest['books'].values())+1024**2+4096
    result=usb.export(backup,'allowed-id',actor=ids['admin'],job_id='c'*32)
    assert result['files']==3 and len(list((root/'Документи').rglob('*.pdf')))==2

def test_storage_measures_no_cleanup_and_seven_day_growth(archive,tmp_path,monkeypatch):
    backup,*_=archive
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def scalar(self,_):return 2048
    monkeypatch.setattr(backup.db_engine,'connect',Connection)
    old=backup.config.root/'permanent.p2b';old.write_bytes(b'keep')
    first=statistics.collect(backup);assert first['growth_7_days'] is None
    first['at']=(datetime.now(UTC)-timedelta(days=7,seconds=1)).isoformat();backup.store.save('statistics',first)
    extra=backup.config.emergency_root/'Excel/old-manual.xlsx';private_dir(extra.parent);extra.write_bytes(b'manual data')
    second=statistics.collect(backup);assert second['growth_7_days']>0 and second['excel']['files']==1
    assert extra.read_bytes()==b'manual data' and old.read_bytes()==b'keep'

def test_offline_restore_plan_never_requires_a_live_source_connection(backup_config,monkeypatch,capsys):
    from app.services import backup as cli
    from app.services.backups import config,engine,restore
    cfg,_=backup_config
    class Fake:
        config=cfg
        store=SimpleNamespace(initialize=lambda:None)
        def operation_lock(self):raise AssertionError('offline recovery must not open a source DB')
    monkeypatch.setattr(config.BackupConfig,'load',lambda settings:cfg)
    monkeypatch.setattr(engine,'BackupEngine',lambda *_:Fake())
    monkeypatch.setattr(cli.os,'geteuid',lambda:0)
    monkeypatch.setattr(restore,'plan',lambda *a,**kw:{'planned':True})
    monkeypatch.setenv('PROJECT2_RESTORE_DATABASE_URL','postgresql+psycopg://synthetic@localhost/project2_restore_12345678')
    assert cli.main(['restore-plan','--offline-master','--id','a'*32,'--reason','Ізольована перевірка'])==0
    assert 'planned' in capsys.readouterr().out

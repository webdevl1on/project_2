"""Isolated infrastructure tests; no real files or personnel."""
from datetime import date, datetime, UTC, timedelta
import sqlite3
from pathlib import Path
import pytest
from sqlalchemy import create_engine, select, func, text, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from app import models
from app.database.base import Base
from app.models import Person, Passport, User, UserSession, DocumentType, PersonDocumentState, PersonDocument, DocumentDetails, DocumentFile, DocumentAudit
from app.services import accounts, documents as docs, document_files as files
from app.services.document_storage import DocumentStorage
from tests.test_name_cases import factory, client


@pytest.fixture
def prepared(factory):
    with factory() as db:
        docs.seed_types(db);db.commit()
        admin=accounts.create_user(db,'admin','Тестовий адміністратор','test-password-123','admin')
        editor=accounts.create_user(db,'editor','Тестовий редактор','test-password-123','editor',actor_id=admin)
        viewer=accounts.create_user(db,'viewer','Тестовий читач','test-password-123','viewer',actor_id=admin)
        person=Person(tax_number='0000000001');other=Person();db.add_all([person,other]);db.commit()
        return admin,editor,viewer,person.person_id,other.person_id


def row(db,pid,key):return next(r for r in docs.list_documents(db,1,pid) if r['id']==key)


def test_accounts_are_personal_passwords_hashed_sessions_revocable(factory,prepared):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        assert db.get(User,admin).password_hash!='test-password-123'
        with pytest.raises(PermissionError):accounts.create_user(db,'second','Другий','test-password-123','admin')
        with pytest.raises(PermissionError):accounts.create_user(db,'unauthorized','Чужий','test-password-123',actor_id=viewer)
        with pytest.raises(ValueError):accounts.create_user(db,'weak','Тест','short',actor_id=admin)
        with pytest.raises(PermissionError):accounts.login(db,'admin','incorrect')
        token,csrf=accounts.login(db,'admin','test-password-123')
        user,session=accounts.authenticate(db,token)
        assert user.id==admin and session.token_hash!=token and len(csrf)==64
        accounts.logout(db,token)
        with pytest.raises(PermissionError):accounts.authenticate(db,token)


def test_failed_login_lock_and_expired_session(factory,prepared):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        for _ in range(5):
            with pytest.raises(PermissionError):accounts.login(db,'admin','wrong')
        assert db.get(User,admin).locked_until is not None
        with pytest.raises(PermissionError):accounts.login(db,'admin','test-password-123')
        db.get(User,admin).locked_until=datetime.now(UTC)-timedelta(minutes=1);db.commit()
        token,_=accounts.login(db,'admin','test-password-123')
        session=db.get(UserSession,accounts.digest_token(token));session.expires_at=datetime.now(UTC)-timedelta(seconds=1);db.commit()
        with pytest.raises(PermissionError):accounts.authenticate(db,token)
        token,_=accounts.login(db,'editor','test-password-123')
        db.get(User,editor).is_active=False;db.commit()
        with pytest.raises(PermissionError):accounts.authenticate(db,token)


def test_presence_contents_and_copies_are_independent(factory,prepared,tmp_path):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        docs.set_presence(db,editor,pid,'driving_license','PRESENT')
        initial=next(r for r in docs.list_documents(db,viewer,pid) if r['type']=='driving_license')
        assert initial['id'] is None and initial['automatic_status']=='NOT_FILLED' and not initial['has_copies']
        key=docs.save(db,editor,pid,'driving_license',{'number':'00012'})
        before=row(db,pid,key)
        assert before['automatic_status']=='PARTIALLY_FILLED' and before['presence']=='PRESENT'
        storage=DocumentStorage(tmp_path/'private')
        files.attach(db,editor,pid,key,before['revision'],b'%PDF-1.7 test','front.pdf','front',storage=storage)
        files.attach(db,editor,pid,key,before['revision'],b'%PDF-1.7 second','back.pdf','back',storage=storage)
        after=row(db,pid,key)
        assert after['has_copies'] and len(after['files'])==2 and after['automatic_status']==before['automatic_status']
        docs.set_presence(db,editor,pid,'driving_license','NEVER_OBTAINED',revision=after['presence_revision'])
        after=row(db,pid,key)
        assert after['presence']=='NEVER_OBTAINED' and after['has_copies'] and after['automatic_status']=='PARTIALLY_FILLED'
        assert not after['needs_requisites'] and not after['needs_copies']


@pytest.mark.parametrize('code',['passport','tax_number','military','birth_certificate'])
def test_primary_never_obtained_rejected_by_service_and_sql(factory,prepared,code):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        with pytest.raises(ValueError):docs.set_presence(db,editor,pid,code,'NEVER_OBTAINED')
        kind=db.scalar(select(DocumentType).where(DocumentType.code==code))
        db.add(PersonDocumentState(person_id=pid,document_type_id=kind.id,presence='NEVER_OBTAINED'))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()


def test_override_requires_permission_reason_preserves_automatic_and_audits(factory,prepared):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        key=docs.save(db,editor,pid,'military',{'number':'0005'})
        current=row(db,pid,key)
        with pytest.raises(PermissionError):docs.override(db,editor,pid,key,current['revision'],'FILLED','Перевірка')
        with pytest.raises(ValueError):docs.override(db,admin,pid,key,current['revision'],'FILLED',' ')
        docs.override(db,admin,pid,key,current['revision'],'FILLED','Погоджена перевірка')
        after=row(db,pid,key)
        assert after['effective_status']=='FILLED' and after['automatic_status']=='PARTIALLY_FILLED'
        assert not after['needs_requisites'] and after['needs_copies']
        assert after['values']==current['values'] and not after['has_copies']
        audits=list(db.scalars(select(DocumentAudit).where(DocumentAudit.document_id==key)))
        assert audits[-1].actor_id==admin and audits[-1].reason=='Погоджена перевірка' and audits[-1].occurred_at
        docs.save(db,editor,pid,'military',{'number':'0006'},key=key,revision=after['revision'])
        assert row(db,pid,key)['effective_status']=='PARTIALLY_FILLED'
        assert list(db.scalars(select(DocumentAudit).where(DocumentAudit.document_id==key)))[-1].changes['override_status']['old']=='FILLED'
        with pytest.raises(IntegrityError):db.execute(text('UPDATE document_audit SET operation=\'hidden\''))
        db.rollback()


def test_raw_sql_owner_guard_and_primary_type_cannot_be_downgraded(factory,prepared):
    admin,editor,viewer,pid,other=prepared
    with factory() as db:
        key=docs.save(db,editor,pid,'passport',{})
        passport=Passport(person_id=other,passport_number='000001');db.add(passport);db.commit();other_key=passport.passport_id
        with pytest.raises(IntegrityError):
            db.execute(text('UPDATE person_documents SET passport_id=:passport WHERE id=:key'),{'passport':other_key,'key':key})
        db.rollback()
        with pytest.raises(IntegrityError):db.execute(text("UPDATE document_types SET is_primary=0 WHERE code='passport'"))
        db.rollback()
        with pytest.raises(IntegrityError):db.execute(text('DELETE FROM document_audit'))
        db.rollback()


def test_canonical_passport_and_tax_number_no_duplicate_details(factory,prepared):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        key=docs.save(db,editor,pid,'passport',{'subtype':'book','series':'ТТ','number':'000123','issued_by':'Тестовий орган','issued_year':2015})
        document=db.get(PersonDocument,key);passport=db.get(Passport,document.passport_id)
        assert passport.passport_number=='000123' and passport.passport_issued_day is None
        assert db.get(DocumentDetails,key) is None and row(db,pid,key)['automatic_status']=='PARTIALLY_FILLED'
        tax=docs.save(db,editor,pid,'tax_number',{})
        assert row(db,pid,tax)['values']=={'number':'0000000001'} and row(db,pid,tax)['automatic_status']=='FILLED'
        with pytest.raises(ValueError):docs.save(db,editor,pid,'tax_number',{'number':'0000000002'},key=tax,revision=row(db,pid,tax)['revision'])
        assert db.get(Person,pid).tax_number=='0000000001'
        db.add(DocumentDetails(document_id=tax,number='duplicate'))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()


def test_replacement_history_and_files_preserved_failure_rolls_back(factory,prepared,tmp_path):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        first=docs.save(db,editor,pid,'other',{'number':'old'})
        file_id=files.attach(db,editor,pid,first,row(db,pid,first)['revision'],b'%PDF-1.7 old','old.pdf','front',storage=DocumentStorage(tmp_path/'private'))
        rev=row(db,pid,first)['revision']
        with pytest.raises(ValueError):docs.save(db,editor,pid,'other',{'issued_day':31,'issued_month':2,'issued_year':2025},replaces_id=first,revision=rev)
        assert db.get(PersonDocument,first).is_current
        second=docs.save(db,editor,pid,'other',{'number':'new'},replaces_id=first,revision=rev)
        assert not db.get(PersonDocument,first).is_current and db.get(PersonDocument,second).is_current
        assert db.get(DocumentDetails,first).number=='old' and db.get(DocumentFile,file_id).document_id==first
        assert db.get(PersonDocument,second).replaces_id==first
        with pytest.raises(ValueError):docs.save(db,editor,pid,'other',{'number':'stale'},key=second,revision=0)


def test_audit_failure_rolls_back_document_and_file_publication(factory,prepared,tmp_path):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        key=docs.save(db,editor,pid,'other',{})
        storage=DocumentStorage(tmp_path/'private')
        def refuse(*args):raise RuntimeError('synthetic audit failure')
        event.listen(DocumentAudit,'before_insert',refuse)
        try:
            with pytest.raises(RuntimeError):files.attach(db,editor,pid,key,row(db,pid,key)['revision'],b'%PDF-1.7 test','copy.pdf','front',storage=storage)
            with pytest.raises(RuntimeError):docs.save(db,editor,pid,'other',{'number':'not committed'},key=key,revision=row(db,pid,key)['revision'])
        finally:event.remove(DocumentAudit,'before_insert',refuse)
        assert db.scalar(select(func.count()).select_from(DocumentFile))==0 and not list(storage.root.iterdir())
        assert db.get(DocumentDetails,key).number is None


def test_driving_categories_and_expiry_are_separate(factory,prepared):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        key=docs.save(db,editor,pid,'driving_license',{'series':'ТЕ','number':'0001','issued_day':1,'issued_month':1,'issued_year':2020,
            'categories':[{'category':'B','start_day':1,'start_month':1,'start_year':2020,'expire_day':1,'expire_month':1,'expire_year':2021}]})
        result=row(db,pid,key)
        assert result['automatic_status']=='FILLED' and result['expiry']=='UNKNOWN' and result['category_expiry']['B']=='EXPIRED'
        assert docs.expiry({'expire_year':2030},on=date(2026,1,1))=='INCOMPLETE'
        assert docs.expiry({'expire_day':10,'expire_month':1,'expire_year':2026},on=date(2026,1,1),days=10)=='EXPIRING'
        assert docs.expiry({'expiry_mode':'unlimited'})=='UNLIMITED'
        with pytest.raises(ValueError):docs.save(db,editor,pid,'birth_certificate',{'issued_month':3})
        assert docs.calculated_status('other',{'extra':{},'categories':[]})=='NOT_FILLED'


def test_files_private_owner_checked_removed_history_requires_admin(factory,prepared,tmp_path):
    admin,editor,viewer,pid,other=prepared
    with factory() as db:
        key=docs.save(db,editor,pid,'other',{})
        storage=DocumentStorage(tmp_path/'private')
        with pytest.raises(ValueError):files.attach(db,editor,pid,key,row(db,pid,key)['revision'],b'<html>unsafe</html>','fake.pdf','front',storage=storage)
        fid=files.attach(db,editor,pid,key,row(db,pid,key)['revision'],b'%PDF-1.7 private','../../private.pdf','front',storage=storage)
        file,path=files.download(db,viewer,pid,fid,storage=storage)
        assert file.original_name=='private.pdf' and path.is_file()
        with pytest.raises(ValueError):files.download(db,viewer,other,fid,storage=storage)
        files.remove(db,editor,pid,fid,file.revision,'Помилкове завантаження')
        with pytest.raises(ValueError):files.download(db,viewer,pid,fid,storage=storage)
        with pytest.raises(PermissionError):files.download(db,viewer,pid,fid,history=True,storage=storage)
        assert files.download(db,admin,pid,fid,history=True,storage=storage)[1].is_file()
        assert not row(db,pid,key)['has_copies']
        with pytest.raises(ValueError):storage.path('../escape')


def test_file_publication_failure_and_tax_archive_snapshot(factory,prepared,tmp_path,monkeypatch):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        key=docs.save(db,editor,pid,'tax_number',{})
        revision=row(db,pid,key)['revision']
        storage=DocumentStorage(tmp_path/'failure')
        def refuse(prepared):raise OSError('synthetic disk failure')
        monkeypatch.setattr(storage,'publish',refuse)
        with pytest.raises(OSError):files.attach(db,editor,pid,key,revision,b'%PDF-1.7 demo','copy.pdf','front',storage=storage)
        assert not list(storage.root.iterdir()) and not db.scalar(select(func.count()).select_from(DocumentFile))
        docs.archive(db,editor,pid,key,revision)
        # The archived number is only an audit snapshot; Person remains the current source.
        db.get(Person,pid).tax_number='0000000002';db.commit()
        assert row(db,pid,key)['values']['number']=='0000000001'
        assert db.get(DocumentDetails,key) is None


def test_external_canonical_change_does_not_silently_reuse_manual_override(factory,prepared):
    admin,editor,viewer,pid,_=prepared
    with factory() as db:
        key=docs.save(db,editor,pid,'tax_number',{})
        docs.override(db,admin,pid,key,row(db,pid,key)['revision'],'NOT_FILLED','Потрібна повторна перевірка')
        assert row(db,pid,key)['effective_status']=='NOT_FILLED'
        db.get(Person,pid).tax_number='0000000002';db.commit()
        after=row(db,pid,key)
        assert after['override_stale'] and after['effective_status']=='FILLED' and after['override_status']=='NOT_FILLED'


def test_protected_json_api_ignores_legacy_admin_bypass(client,factory,prepared,monkeypatch,tmp_path):
    browser,_=client;admin,editor,viewer,pid,_=prepared
    monkeypatch.setenv('PROJECT2_DEV_ADMIN_OPEN','1')
    monkeypatch.setenv('PROJECT2_DOCUMENT_STORAGE',str(tmp_path/'private'))
    assert browser.get(f'/persons/{pid}/documents').status_code==401
    login=browser.post('/auth/login',json={'username':'editor','password':'test-password-123'})
    assert login.status_code==200 and 'HttpOnly' in login.headers['set-cookie'] and 'Secure' in login.headers['set-cookie']
    csrf=login.json()['csrf_token']
    assert browser.post(f'/persons/{pid}/documents',json={'type':'other','details':{}}).status_code==403
    response=browser.post(f'/persons/{pid}/documents',json={'type':'other','details':{'number':'0001'},'actor_id':viewer},headers={'X-CSRF-Token':csrf})
    assert response.status_code==200
    key=response.json()['id']
    with factory() as db:assert db.scalar(select(DocumentAudit).where(DocumentAudit.document_id==key)).actor_id==editor
    response=browser.get(f'/persons/{pid}/documents?code=other&copies=false&current=true')
    assert response.status_code==200 and response.headers['cache-control']=='no-store' and response.json()['documents'][0]['id']==key
    rev=response.json()['documents'][0]['revision']
    upload=browser.post(f'/persons/{pid}/documents/{key}/files',headers={'X-CSRF-Token':csrf},data={'revision':rev,'side':'front'},files={'file':('front.pdf',b'%PDF-1.7 demo','application/pdf')})
    assert upload.status_code==200
    download=browser.get(f'/persons/{pid}/documents/files/{upload.json()["id"]}')
    assert download.status_code==200 and download.content==b'%PDF-1.7 demo' and download.headers['x-content-type-options']=='nosniff'
    assert browser.post('/auth/logout',headers={'X-CSRF-Token':csrf}).status_code==200
    assert browser.get(f'/persons/{pid}/documents').status_code==401


def old_database(path):
    from app.models.documents import NEW_TABLE_NAMES
    engine=create_engine('sqlite:///'+str(path))
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name not in NEW_TABLE_NAMES])
    with sessionmaker(bind=engine)() as db:
        p=Person(tax_number='0000000001');db.add(p);db.flush()
        db.add_all([Passport(person_id=p.person_id,passport_number='00123',passport_issued_year=2015,is_active=True),
                    Passport(person_id=p.person_id,passport_number='00456',passport_issued_year=2010,is_active=True)])
        db.commit()
    engine.dispose()


def test_migration_preserves_canonical_data_triggers_unknown_presence_and_idempotence(tmp_path):
    from app.database.migrate_documents import migrate
    path=tmp_path/'prior.sqlite3';old_database(path)
    with sqlite3.connect(path) as db:
        people=db.execute('SELECT * FROM persons').fetchall();passports=db.execute('SELECT * FROM passports').fetchall()
        triggers=db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
    backup=migrate(path);assert backup.is_file() and backup.stat().st_mode&0o777==0o600
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM persons').fetchall()==people and db.execute('SELECT * FROM passports').fetchall()==passports
        assert set(triggers)<=set(db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall())
        assert db.execute('SELECT count(*) FROM document_details').fetchone()==(0,)
        assert db.execute('SELECT count(*) FROM person_document_states').fetchone()==(0,)
        assert db.execute('SELECT count(*) FROM users').fetchone()==(0,)
        assert db.execute('SELECT count(*) FROM person_documents WHERE passport_id IS NOT NULL AND is_current=1').fetchone()==(0,)
        assert db.execute('SELECT count(*) FROM person_documents').fetchone()==(3,)
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert migrate(path) is None


def test_migration_failure_ddl_rollback_and_backup(tmp_path,monkeypatch):
    from app.database import migrate_documents as migration
    from app.models.documents import NEW_TABLE_NAMES
    path=tmp_path/'failure.sqlite3';old_database(path)
    original=migration.create_table
    def fail(db,table):
        original(db,table)
        if table.name=='person_documents':raise RuntimeError('DDL failure')
    monkeypatch.setattr(migration,'create_table',fail)
    with pytest.raises(RuntimeError):migration.migrate(path)
    with sqlite3.connect(path) as db:
        assert not NEW_TABLE_NAMES&{r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert db.execute('SELECT count(*) FROM passports').fetchone()==(2,)
    assert len(list(tmp_path.glob('*.before-documents-*.sqlite3')))==1

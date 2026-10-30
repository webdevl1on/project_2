"""Medical facts use synthetic people, isolated SQLite and private temporary files."""
from datetime import date
import sqlite3
import pytest
from sqlalchemy import select,func,text,create_engine
from sqlalchemy.exc import IntegrityError
from app.database.base import Base
from app.models import MedicalExam,Injury,Award,DnaSample,PersonnelTask,MedicalSelection,MedicalDocumentLink,PersonnelAudit,PersonDocument,Person,User
from app.services import medical as service,document_files,documents
from app.services.document_storage import DocumentStorage
from tests.test_documents import prepared
from tests.test_name_cases import factory,client


def create(db,pid,kind,**fields):return service.save(db,1,pid,kind,fields)['id']
def edit(db,pid,kind,key,**changes):
    row=service.record(db,pid,kind,key)
    fields={f[0]:getattr(row,f[0]) for f in service.FORM_FIELDS[kind]}
    return service.save(db,1,pid,kind,{**fields,**changes},key=key,revision=row.revision)
def count(db,model):return db.scalar(select(func.count()).select_from(model))
def task(db,pid):return service.Repo.rows(db,'tasks',pid)[0]

@pytest.mark.parametrize('basis',['INJURY','ILLNESS','OTHER'])
def test_exam_bases_repeat_and_incomplete_control(factory,prepared,basis):
    pid=prepared[3]
    with factory() as db:
        injury=create(db,pid,'injuries',description='Тестове поранення') if basis=='INJURY' else None
        first=create(db,pid,'exams',basis=basis,injury_id=injury,status='NEEDS_EXAM')
        second=create(db,pid,'exams',basis=basis,injury_id=injury,status='PLANNED',planned_on='2026-06-03')
        assert service.active_exam(db,pid)==(None,None)
        with pytest.raises(ValueError,match='лише завершене'):service.select_active(db,1,pid,second)
        assert len(service.page(db,1,pid)['pending_exams'])==2
        edit(db,pid,'exams',first,status='COMPLETED',issued_on='2026-06-04',fitness='FIT')
        assert service.active_exam(db,pid)[0].id==first
        assert len(service.page(db,1,pid)['pending_exams'])==1
        assert service.record(db,pid,'exams',second).injury_id==injury


def test_active_selection_manual_survives_newer_and_reset(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        first=create(db,pid,'exams',status='COMPLETED',issued_on='2025-01-01',fitness='FIT')
        second=create(db,pid,'exams',status='COMPLETED',issued_on='2026-01-01',fitness='UNFIT')
        assert service.active_exam(db,pid)[0].id==second
        service.select_active(db,1,pid,first)
        newest=create(db,pid,'exams',status='COMPLETED',issued_on='2026-02-01',fitness='FIT_SUPPORT')
        assert service.active_exam(db,pid)[0].id==first
        with pytest.raises(ValueError,match='скасуйте'):edit(db,pid,'exams',first,status='PLANNED',fitness=None)
        choice=db.get(MedicalSelection,pid)
        service.select_active(db,1,pid,None,choice.revision)
        assert service.active_exam(db,pid)[0].id==newest

@pytest.mark.parametrize('issued',['2026-01-01',None])
def test_ambiguous_latest_date_never_arbitrary(factory,prepared,issued):
    pid=prepared[3]
    with factory() as db:
        first=create(db,pid,'exams',status='COMPLETED',issued_on='2026-01-01')
        create(db,pid,'exams',status='COMPLETED',issued_on=issued)
        assert service.active_exam(db,pid)[0] is None
        assert 'однакові або відсутні' in service.active_exam(db,pid)[1]
        service.select_active(db,1,pid,first)
        assert service.active_exam(db,pid)[0].id==first

@pytest.mark.parametrize('value',['15._.2026','_.03.2026','2026-02-30','20260301','2026-01',True])
def test_exact_subject_dates_reject_partial_invalid(factory,prepared,value):
    with factory() as db:
        with pytest.raises(ValueError):create(db,prepared[3],'exams',issued_on=value)
        assert count(db,MedicalExam)==0


def test_injury_independent_unknown_dates_no_fake_exam_award_and_idempotent_task(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        key=create(db,pid,'injuries',description='Без відомої дати',exam_not_needed=True)
        edit(db,pid,'injuries',key,area='Тестовий район')
        assert count(db,MedicalExam)==count(db,Award)==0
        assert count(db,PersonnelTask)==1
        assert db.get(Injury,key).occurred_on is None
        assert task(db,pid).status=='OPEN'

@pytest.mark.parametrize('status',list(service.AWARD_STATES))
def test_status_alone_is_not_evidence(factory,prepared,status):
    pid=prepared[3]
    with factory() as db:
        injury=create(db,pid,'injuries')
        create(db,pid,'awards',injury_id=injury,status=status)
        assert task(db,pid).status=='OPEN'

@pytest.mark.parametrize('mode',['submission','refusal'])
def test_confirmed_evidence_completes_task_preserves_submission_and_reopens(factory,prepared,mode):
    pid=prepared[3]
    with factory() as db:
        injury=create(db,pid,'injuries')
        fields={'submission_confirmed':True,'submission_on':'2026-01-01','submission_number':'0001'} if mode=='submission' else {'refusal_confirmed':True,'refusal_on':'2026-01-01','refusal_number':'0002','refusal_reason':'Тестове обґрунтування'}
        key=create(db,pid,'awards',injury_id=injury,**fields)
        assert task(db,pid).status=='COMPLETED'
        service.save(db,1,pid,'awards',{'status':'AWARDED'},key=key,revision=db.get(Award,key).revision)
        assert task(db,pid).status=='COMPLETED'
        assert task(db,pid).award_id==key
        assert getattr(db.get(Award,key),mode+'_on')==date(2026,1,1)
        edit(db,pid,'awards',key,**{mode+'_confirmed':False})
        assert task(db,pid).status=='OPEN'


def test_manual_task_decision_preserved_with_warning_and_history(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        injury=create(db,pid,'injuries');t=task(db,pid)
        with pytest.raises(ValueError,match='причину'):edit(db,pid,'tasks',t.id,status='CANCELLED')
        edit(db,pid,'tasks',t.id,status='CANCELLED',decision_reason='Перевірено вручну')
        result=edit(db,pid,'injuries',injury,description='Уточнення')
        assert task(db,pid).status=='CANCELLED' and result['warnings']
        manual=create(db,pid,'tasks',title='Інше кадрове питання',responsible='Тестовий відповідальний')
        edit(db,pid,'tasks',manual,note='Уточнення')
        assert any(r.operation=='update' and r.entity=='tasks' for r in service.Repo.audits(db,pid))
        assert count(db,Award)==0


def test_award_without_injury_and_dna_history(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        award=create(db,pid,'awards',name='Тестова нагорода')
        assert db.get(Award,award).injury_id is None and count(db,Injury)==0
        first=create(db,pid,'dna',envelope_number='0000123',collected_on='2026-02-03',storage_unit='Тестова частина')
        edit(db,pid,'dna',first,storage_unit='Уточнена частина')
        create(db,pid,'dna',envelope_number='0000456',collected_on='2026-04-05')
        assert count(db,DnaSample)==2
        with pytest.raises(ValueError):create(db,pid,'dna')


def test_revision_owner_roles_and_atomic_audit_failure(factory,prepared,monkeypatch):
    pid,other=prepared[3:]
    with factory() as db:
        injury=create(db,pid,'injuries')
        with pytest.raises(ValueError):create(db,other,'exams',basis='INJURY',injury_id=injury)
        with pytest.raises(ValueError):service.select_active(db,1,pid,999)
        with pytest.raises(PermissionError):service.save(db,prepared[2],pid,'injuries',{})
        with pytest.raises(ValueError):service.save(db,1,pid,'injuries',{},key=injury,revision=999)
        before=count(db,Injury),count(db,PersonnelTask),count(db,PersonnelAudit)
        def fail(*args,**kwargs):raise ValueError('Тестова відмова аудиту')
        monkeypatch.setattr(service,'audit',fail)
        with pytest.raises(ValueError):create(db,pid,'injuries')
        assert before==(count(db,Injury),count(db,PersonnelTask),count(db,PersonnelAudit))
        before_docs=count(db,PersonDocument),count(db,MedicalDocumentLink)
        with pytest.raises(ValueError):service.link_document(db,1,pid,'injuries',injury,'form100',revision=db.get(Injury,injury).revision)
        assert before_docs==(count(db,PersonDocument),count(db,MedicalDocumentLink))


def test_multiple_document_categories_files_and_independent_existing_document(factory,prepared,tmp_path):
    pid,other=prepared[3:]
    storage=DocumentStorage(tmp_path/'copies')
    with factory() as db:
        injury=create(db,pid,'injuries')
        for category in ('form100','combat_certificate','circumstances','discharge','form100'):
            doc=service.link_document(db,1,pid,'injuries',injury,category,revision=db.get(Injury,injury).revision)
            for name in ('front.pdf','back.pdf'):
                file_id=document_files.attach(db,1,pid,doc,db.get(PersonDocument,doc).revision,b'%PDF-1.7 synthetic',name,'page',storage=storage)
                assert document_files.download(db,prepared[2],pid,file_id,storage=storage)[1].is_file()
                with pytest.raises(ValueError):document_files.download(db,1,other,file_id,storage=storage)
        assert count(db,MedicalDocumentLink)==5
        assert sum(len(r['files']) for r in service.page(db,1,pid)['links'])==10
        independent=documents.save(db,1,pid,'other',{'number':'123'})
        exam=create(db,pid,'exams',basis='ILLNESS')
        service.link_document(db,1,pid,'exams',exam,'recommendation',document_id=independent,revision=db.get(MedicalExam,exam).revision)
        with pytest.raises(ValueError):service.link_document(db,1,pid,'exams',exam,'form100',revision=1)
        assert all(r.actor_id==1 for r in service.Repo.audits(db,pid))


def test_raw_sql_owner_calendar_and_append_only_guards(factory,prepared):
    pid,other=prepared[3:]
    with factory() as db:
        injury=create(db,pid,'injuries')
        for sql,params in [("UPDATE person_injuries SET occurred_on='2026-02-30' WHERE id=:id",{'id':injury}),('UPDATE personnel_audit SET operation=\'fake\'',{}),('DELETE FROM personnel_audit',{})]:
            with pytest.raises(IntegrityError):db.execute(text(sql),params);db.commit()
            db.rollback()
        with pytest.raises(IntegrityError):
            db.add(MedicalExam(person_id=other,injury_id=injury,basis='INJURY'));db.commit()
        db.rollback()


def previous_schema(path):
    from app.models.medical import NEW_TABLE_NAMES
    engine=create_engine('sqlite:///'+str(path))
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name not in NEW_TABLE_NAMES])
    with engine.begin() as connection:connection.execute(Person.__table__.insert().values(tax_number='0000000001'))
    engine.dispose()


def test_additive_migration_backup_idempotence_no_data_loss(tmp_path):
    from app.database.migrate_medical import migrate
    from app.models.medical import NEW_TABLE_NAMES,GUARDS
    path=tmp_path/'medical-test.sqlite3';previous_schema(path)
    backup=migrate(path);assert backup.is_file() and migrate(path) is None
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT tax_number FROM persons').fetchall()==[('0000000001',)]
        assert NEW_TABLE_NAMES <= {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert GUARDS <= {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='trigger'")}
    with sqlite3.connect(backup) as db:assert not NEW_TABLE_NAMES & {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_migration_ddl_failure_rolls_back(tmp_path,monkeypatch):
    from app.database import migrate_medical as migration
    from app.models.medical import NEW_TABLE_NAMES
    path=tmp_path/'rollback-test.sqlite3';previous_schema(path)
    original=migration.create_table
    def fail(db,table):original(db,table);raise ValueError('synthetic failure')
    monkeypatch.setattr(migration,'create_table',fail)
    with pytest.raises(ValueError):migration.migrate(path)
    with sqlite3.connect(path) as db:assert not NEW_TABLE_NAMES & {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert list(tmp_path.glob('*.before-medical-*.sqlite3'))


def test_staff_table_active_exam_scalar_filters_dates_sorting_and_no_multiplication(factory,prepared):
    from tests.test_person_positions import make_position
    from app.models import PersonAssignment
    from app.services.service_person_positions import ServicePersonPositionFunc as Table
    from app.utils.date_query import DateFilter
    pid,other=prepared[3:]
    with factory() as db:
        db.info['legacy_staff_fixture']=True
        position=make_position(10,'Тестовий підрозділ','Посада','Тестова посада')
        vacant=make_position(20,'Інший','Вакансія','Вакантна посада')
        db.add_all([position,vacant]);db.flush()
        db.add(PersonAssignment(person_id=pid,position_id=position.position_id));db.commit()
        old=create(db,pid,'exams',status='COMPLETED',issued_on='2026-01-01',fitness='FIT')
        create(db,pid,'exams',status='PLANNED')
        latest=create(db,pid,'exams',status='COMPLETED',issued_on='2026-03-01',fitness='UNFIT',institution='Тестова ВЛК',number='0001')
        create(db,pid,'injuries',occurred_on='2026-02-01')
        create(db,pid,'dna',collected_on='2026-04-01',envelope_number='000099')
        result=Table.get_positions(db)
        assert result['total']==2
        occupied=next(r for r in result['rows'] if r['assignment'])
        assert occupied['values']['medical_fitness']=='Непридатний'
        assert occupied['values']['medical_number']=='0001'
        assert occupied['values']['medical_issued_on']=='01.03.2026'
        assert occupied['values']['dna_envelope_number']=='000099'
        assert Table.get_positions(db,column_filters={'medical_fitness':['UNFIT']})['total']==1
        assert Table.get_positions(db,column_filters={'medical_issued_on':[DateFilter.from_json({'months':[3]}).to_json()]})['total']==1
        assert Table.get_positions(db,column_filters={'latest_injury_date':[DateFilter.from_json({'months':[2]}).to_json()]})['total']==1
        assert Table.get_positions(db,column_filters={'pending_exam_count':['1']})['total']==1
        assert Table.get_positions(db,sort_by='medical_issued_on',direction='desc')['rows'][0]['assignment']
        service.select_active(db,1,pid,old)
        assert Table.get_positions(db,column_filters={'medical_fitness':['FIT']})['total']==1
        service.select_active(db,1,pid,None,db.get(MedicalSelection,pid).revision)
        create(db,pid,'exams',status='COMPLETED',issued_on='2026-03-01',fitness='FIT')
        result=Table.get_positions(db)
        assert result['total']==2 and result['data_warnings']
        assert next(r for r in result['rows'] if r['assignment'])['values']['medical_fitness']=='-'


def test_protected_api_rejects_anonymous_csrf_and_viewer_writes(client,prepared,monkeypatch):
    browser,_=client;pid=prepared[3]
    monkeypatch.setenv('PROJECT2_AUTH_ALLOW_LOCAL_HTTP','1')
    monkeypatch.setenv('PROJECT2_DEV_ADMIN_OPEN','1')
    assert browser.get(f'/persons/{pid}/medical').status_code==401
    login=browser.post('/auth/login',json={'username':'viewer','password':'test-password-123'})
    csrf=login.json()['csrf_token']
    assert browser.get(f'/persons/{pid}/medical').status_code==200
    assert browser.post(f'/persons/{pid}/medical/injuries',json={'fields':{}}).status_code==403
    assert browser.post(f'/persons/{pid}/medical/injuries',json={'fields':{}},headers={'X-CSRF-Token':csrf}).status_code==403


def test_manual_reason_on_already_completed_automatic_task_preserves_decision(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        injury=create(db,pid,'injuries')
        award=create(db,pid,'awards',injury_id=injury,submission_confirmed=True,submission_on='2026-01-01',submission_number='001')
        automatic=task(db,pid)
        assert automatic.status=='COMPLETED' and not automatic.manual_decision
        edit(db,pid,'tasks',automatic.id,decision_reason='Окремо перевірено вручну')
        assert task(db,pid).manual_decision
        result=edit(db,pid,'awards',award,submission_confirmed=False)
        assert task(db,pid).status=='COMPLETED' and result['warnings']

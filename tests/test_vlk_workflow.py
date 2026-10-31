"""Independent VLK dates and per-exam controls, isolated SQLite only."""
from datetime import date
import re
import sqlite3
import pytest
from sqlalchemy import select,text,func
from app.models import MedicalExam,PersonnelTask,MedicalSelection,MedicalDocumentLink,PersonDocument
from app.services import medical as service,documents
from app.medical_catalog import fitness_label
from tests.test_documents import prepared
from tests.test_name_cases import factory
from tests.test_medical import create,edit,legacy_exam


def save(db,pid,**fields):return service.save(db,1,pid,'exams',fields)['id']
def controls(db,pid):return [t for t in service.Repo.rows(db,'tasks',pid) if t.kind in ('injury_vlk','exam_vlk') and t.status!='CANCELLED']

@pytest.mark.parametrize('status,extra',[('NEEDS_EXAM',{}),('PLANNED',{'planned_on':'2035-01-01'}),('COMPLETED',{'issued_on':'2035-01-03','number':'001','fitness':'FIT'})])
def test_three_creatable_states_and_future_dates_are_not_proof_of_completion(factory,prepared,status,extra):
    with factory() as db:
        key=save(db,prepared[3],basis_note='Підстава',status=status,**extra)
        row=db.get(MedicalExam,key);assert row.status==status and row.ended_on is None
        assert controls(db,prepared[3])[0].status==('COMPLETED' if status=='COMPLETED' else 'OPEN')

@pytest.mark.parametrize('fields',[{}, {'status':'PLANNED','basis_note':'Підстава'}, {'status':'COMPLETED'}, {'status':'COMPLETED','issued_on':'2026-01-01','number':'001'}, {'status':'INTERRUPTED','planned_on':'2026-01-01','interrupted_on':'2026-01-02','interruption_reason':'Причина'}])
def test_required_fields_and_no_new_interrupted(factory,prepared,fields):
    with factory() as db:
        with pytest.raises(ValueError):save(db,prepared[3],**fields)
        assert db.scalar(select(func.count()).select_from(MedicalExam))==0


def test_basis_alternatives_independent_document_and_wrong_owner(factory,prepared):
    pid,other=prepared[3:]
    with factory() as db:
        injury=create(db,pid,'injuries')
        save(db,pid,basis='INJURY',injury_id=injury)
        doc=documents.save(db,1,pid,'other',{'number':'basis'})
        key=service.save(db,1,pid,'exams',{'basis':'ILLNESS'},basis_document_id=doc)['id']
        assert any(l.exam_id==key and l.document_id==doc for l in service.Repo.links(db,pid))
        with pytest.raises(ValueError):service.save(db,1,other,'exams',{},basis_document_id=doc)
        save(db,pid,basis='OTHER',basis_note='Опис')


def test_interruption_only_from_plan_dates_reason_new_exam_and_new_referral(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        first=save(db,pid,basis_note='Причина')
        with pytest.raises(ValueError):edit(db,pid,'exams',first,status='INTERRUPTED',interrupted_on='2026-02-02',interruption_reason='Причина')
        edit(db,pid,'exams',first,status='PLANNED',planned_on='2026-02-01')
        for end,reason in [('2026-01-31','Причина'),('2026-02-02',None)]:
            with pytest.raises(ValueError):edit(db,pid,'exams',first,status='INTERRUPTED',interrupted_on=end,interruption_reason=reason)
        doc=service.link_document(db,1,pid,'exams',first,'referral',revision=db.get(MedicalExam,first).revision)
        edit(db,pid,'exams',first,status='INTERRUPTED',interrupted_on='2026-02-02',interruption_reason='Перервано')
        assert controls(db,pid)[0].status=='OPEN' and service.active_exam(db,pid)[0] is None
        with pytest.raises(ValueError):edit(db,pid,'exams',first,status='PLANNED',interrupted_on=None,interruption_reason=None)
        second=save(db,pid,basis_note='Та сама підстава',status='PLANNED',planned_on='2026-03-01')
        with pytest.raises(ValueError):service.link_document(db,1,pid,'exams',second,'referral',document_id=doc,revision=db.get(MedicalExam,second).revision)
        assert not any(l.exam_id==second for l in service.Repo.links(db,pid))
        assert db.get(MedicalExam,first).status=='INTERRUPTED'


def test_dates_are_independent_calendar_order_enforced(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        key=save(db,pid,status='COMPLETED',planned_on='2035-01-01',ended_on='2035-01-03',issued_on='2035-01-06',number='001',fitness='FIT_SUPPORT')
        r=db.get(MedicalExam,key);assert (r.planned_on,r.ended_on,r.issued_on)==(date(2035,1,1),date(2035,1,3),date(2035,1,6))
        for changes in [{'ended_on':'2034-12-31'},{'issued_on':'2035-01-02'},{'interrupted_on':'2035-01-02'}]:
            with pytest.raises(ValueError):edit(db,pid,'exams',key,**changes)
        assert fitness_label('FIT_SUPPORT')=='Обмежено придатний'
        assert fitness_label('FIT_SUPPORT',official=True)=='Придатний до служби в тилових частинах забезпечення'


def test_new_passage_not_completed_by_old_passage_no_duplicate_and_manual_not_needed(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        injury=create(db,pid,'injuries')
        first=create(db,pid,'exams',basis='INJURY',injury_id=injury,status='COMPLETED')
        second=save(db,pid,basis='INJURY',injury_id=injury)
        live=controls(db,pid)
        assert len(live)==2 and next(t for t in live if t.exam_id==first).status=='COMPLETED'
        assert next(t for t in live if t.exam_id==second).status=='OPEN'
        edit(db,pid,'exams',second,basis_note='Уточнено')
        assert len(controls(db,pid))==2
        assert service.active_exam(db,pid)[0].id==first
        service.select_active(db,1,pid,first)
        with pytest.raises(ValueError):service.select_active(db,1,pid,second,db.get(MedicalSelection,pid).revision)
        task=next(t for t in live if t.kind=='injury_vlk')
        service.vlk_decision(db,1,pid,task.id,'not_needed','Явна причина',task.revision)
        assert next(t for t in controls(db,pid) if t.exam_id==second).status=='OPEN'
        assert next(t for t in controls(db,pid) if t.kind=='injury_vlk').manual_decision


def test_legacy_completed_kept_and_sorted_current_read_but_edit_requires_fields(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        old=legacy_exam(db,pid,status='COMPLETED',issued_on=date(2025,1,1),fitness='FIT')
        service.select_active(db,1,pid,old)
        new=save(db,pid,basis_note='Причина')
        data=service.page(db,1,pid)
        assert data['exams'][0]['id']==new and data['active_exam']['id']==old
        assert next(r for r in data['exams'] if r['id']==old)['is_current']
        with pytest.raises(ValueError):service.save(db,1,pid,'exams',{'diagnosis':'Уточнено'},key=old,revision=db.get(MedicalExam,old).revision)
        assert db.get(MedicalExam,old).number is None and db.get(MedicalExam,old).status=='COMPLETED'


def old_schema(path):
    """Downgrade only the two evolving tables to the previous committed DDL."""
    from sqlalchemy import create_engine
    from app.database.base import Base
    engine=create_engine('sqlite:///'+str(path));Base.metadata.create_all(engine);engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA foreign_keys=OFF')
        triggers=db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
        for name,_ in triggers:db.execute('DROP TRIGGER "'+name+'"')
        for table,remove in [('person_medical_exams',{'ended_on','interrupted_on','interruption_reason'}),('personnel_tasks',{'exam_id'})]:
            ddl=db.execute('SELECT sql FROM sqlite_master WHERE name=?',(table,)).fetchone()[0]
            lines=ddl.splitlines();lines=[l for l in lines if not any(re.match(r'\s*'+k+r'\s',l) or ('FOREIGN KEY('+k+')') in l for k in remove)]
            ddl='\n'.join(lines).replace(",'INTERRUPTED'",'')
            ddl=re.sub(r',\s*\n\)',r'\n)',ddl)
            indexes=db.execute("SELECT name,sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",(table,)).fetchall()
            db.execute('DROP TABLE '+table);db.execute(ddl)
            for name,sql in indexes:
                if name!='one_exam_control_task':db.execute(sql)
        for name,sql in triggers:
            for field in ('ended_on','interrupted_on'):
                check=f"(NEW.{field} IS NOT NULL AND (length(NEW.{field})!=10 OR NEW.{field}<'0001-01-01' OR date(NEW.{field},'+0 days') IS NULL OR date(NEW.{field},'+0 days')!=NEW.{field}))"
                sql=sql.replace(check+' OR ','').replace(' OR '+check,'')
            sql=sql.replace(' OR length(NEW.interruption_reason)>2000','')
            sql=sql.replace("(NEW.exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_medical_exams e WHERE e.id=NEW.exam_id AND e.person_id=NEW.person_id)) OR ",'')
            if name not in ('medical_exam_no_new_interrupted','medical_exam_interrupted_history'):db.execute(sql)
        # Legacy incomplete completed row, manually selected, with a linked old document.
        db.execute("INSERT INTO persons(person_id) VALUES(900)")
        db.execute("INSERT INTO person_medical_exams(id,person_id,status,basis,issued_on,planned_on,created_at,updated_at,revision) VALUES(900,900,'COMPLETED','ILLNESS','2025-01-03','2025-01-01','2025-01-01','2025-01-01',7)")
        db.execute("INSERT INTO person_medical_selections(person_id,exam_id,created_at,updated_at,revision) VALUES(900,900,'2025-01-01','2025-01-01',1)")
        kind=db.execute("SELECT id FROM document_types WHERE code='other'").fetchone()[0]
        db.execute("INSERT INTO person_documents(id,person_id,document_type_id,is_current,created_at,updated_at,revision) VALUES(900,900,?,0,'2025-01-01','2025-01-01',1)",(kind,))
        db.execute("INSERT INTO medical_document_links(document_id,exam_id,category,created_at,updated_at,revision) VALUES(900,900,'recommendation','2025-01-01','2025-01-01',1)")


def test_workflow_migration_keeps_ids_dates_fk_legacy_and_noop(tmp_path):
    from app.database.migrate_vlk_workflow import migrate
    path=tmp_path/'workflow_test.sqlite3';old_schema(path)
    backup=migrate(path);assert backup.is_file() and migrate(path) is None
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT id,status,planned_on,issued_on,ended_on,number,fitness,revision FROM person_medical_exams').fetchone()==(900,'COMPLETED','2025-01-01','2025-01-03',None,None,None,7)
        assert db.execute('SELECT exam_id FROM person_medical_selections').fetchone()==(900,)
        assert db.execute('SELECT exam_id FROM medical_document_links').fetchone()==(900,)
    with sqlite3.connect(backup) as db:assert 'ended_on' not in {r[1] for r in db.execute('PRAGMA table_info(person_medical_exams)')}


def test_workflow_migration_failure_rolls_back_table_rebuild(tmp_path,monkeypatch):
    from app.database import migrate_vlk_workflow as migration
    path=tmp_path/'rollback_test.sqlite3';old_schema(path)
    original=migration.upgrade
    def fail(db):original(db);raise ValueError('Тестова відмова після DDL')
    monkeypatch.setattr(migration,'upgrade',fail)
    with pytest.raises(ValueError):migration.migrate(path)
    with sqlite3.connect(path) as db:
        assert 'ended_on' not in {r[1] for r in db.execute('PRAGMA table_info(person_medical_exams)')}
        assert db.execute('SELECT id FROM person_medical_exams').fetchone()==(900,)

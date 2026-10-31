"""Decision first, no invented exams; one atomic VLK task per injury."""
from datetime import date
import sqlite3
import pytest
from sqlalchemy import select,func,text
from app.models import Injury,MedicalExam,PersonnelTask,PersonnelAudit
from app.services import medical as service
from tests.test_documents import prepared
from tests.test_name_cases import factory
from tests.test_medical import create,edit


def task(db,pid,injury):return next(t for t in service.Repo.rows(db,'tasks',pid) if t.kind=='injury_vlk' and t.injury_id==injury)
def view(db,pid,injury):return next(t for t in service.page(db,1,pid)['tasks'] if t['kind']=='injury_vlk' and t['injury_id']==injury)
def decide(db,pid,injury,action,reason):
    t=task(db,pid,injury);service.vlk_decision(db,1,pid,t.id,action,reason,t.revision)


def test_new_injury_no_decision_no_exam_and_idempotent_tasks(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        injury=create(db,pid,'injuries')
        assert task(db,pid,injury).status=='OPEN'
        assert view(db,pid,injury)['stage']=='WAITING_DECISION'
        assert not db.get(Injury,injury).exam_not_needed
        assert db.scalar(select(func.count()).select_from(MedicalExam))==0
        edit(db,pid,'injuries',injury,description='Уточнено')
        assert len(service.Repo.rows(db,'tasks',pid))==2
        with pytest.raises(ValueError):create(db,pid,'injuries',exam_not_needed=True)


def test_not_needed_requires_reason_explicit_reopen_audit_and_generic_edit_guard(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        injury=create(db,pid,'injuries');t=task(db,pid,injury)
        with pytest.raises(ValueError,match='причину'):decide(db,pid,injury,'not_needed','  ')
        assert task(db,pid,injury).status=='OPEN'
        with pytest.raises(ValueError):edit(db,pid,'tasks',t.id,status='COMPLETED',decision_reason='Не через дію')
        decide(db,pid,injury,'not_needed','Медичне обґрунтування')
        assert db.get(Injury,injury).exam_not_needed
        assert view(db,pid,injury)['stage']=='NOT_NEEDED'
        assert task(db,pid,injury).decision_reason=='Медичне обґрунтування'
        exam=create(db,pid,'exams',basis='INJURY',injury_id=injury,status='PLANNED')
        edit(db,pid,'exams',exam,status='COMPLETED')
        edit(db,pid,'exams',exam,status='NEEDS_EXAM')
        assert view(db,pid,injury)['stage']=='NOT_NEEDED'
        decide(db,pid,injury,'reopen','Помилково внесене рішення')
        assert not db.get(Injury,injury).exam_not_needed
        assert task(db,pid,injury).status=='OPEN'
        assert view(db,pid,injury)['stage']=='WAITING_EXAM'
        entries=service.Repo.audits(db,pid)
        assert any(e.operation=='vlk_decision' and e.changes.get('decision',{}).get('new',{}).get('reason')=='Помилково внесене рішення' for e in entries)
        assert all(e.actor_id==1 for e in entries)

@pytest.mark.parametrize('status',['NEEDS_EXAM','PLANNED'])
def test_pending_exam_is_not_completion_and_repeated_completed_any_is_sufficient(factory,prepared,status):
    pid=prepared[3]
    with factory() as db:
        injury=create(db,pid,'injuries')
        first=create(db,pid,'exams',basis='INJURY',injury_id=injury,status=status)
        assert task(db,pid,injury).status=='OPEN'
        assert view(db,pid,injury)['exam_ids']==[first]
        edit(db,pid,'exams',first,status='COMPLETED')
        assert task(db,pid,injury).status=='COMPLETED'
        second=create(db,pid,'exams',basis='INJURY',injury_id=injury,status='COMPLETED')
        edit(db,pid,'exams',first,status='PLANNED')
        assert task(db,pid,injury).status=='COMPLETED'
        edit(db,pid,'exams',second,status='NEEDS_EXAM')
        assert task(db,pid,injury).status=='OPEN'
        assert len([t for t in service.Repo.rows(db,'tasks',pid) if t.kind=='injury_vlk'])==1
        assert any(e.operation=='automatic_sync' and e.entity_id==task(db,pid,injury).id for e in service.Repo.audits(db,pid))


def test_relink_exam_recalculates_both_injuries_award_unaffected(factory,prepared):
    pid=prepared[3]
    with factory() as db:
        first=create(db,pid,'injuries');second=create(db,pid,'injuries')
        exam=create(db,pid,'exams',basis='INJURY',injury_id=first,status='COMPLETED')
        edit(db,pid,'exams',exam,injury_id=second)
        assert task(db,pid,first).status=='OPEN' and task(db,pid,second).status=='COMPLETED'
        create(db,pid,'awards',injury_id=first,submission_on='2026-01-01',submission_number='001',submission_confirmed=True)
        awardtask=next(t for t in service.Repo.rows(db,'tasks',pid) if t.kind=='injury_award' and t.injury_id==first)
        assert awardtask.status=='COMPLETED' and task(db,pid,first).status=='OPEN'
        edit(db,pid,'exams',exam,injury_id=None,basis='ILLNESS')
        assert task(db,pid,second).status=='OPEN'


def test_decision_failure_rolls_back_both_fact_and_task(factory,prepared,monkeypatch):
    pid=prepared[3]
    with factory() as db:
        injury=create(db,pid,'injuries')
        original=service.audit
        def fail(*args,**kwargs):
            if args[3]=='tasks':raise ValueError('Тестова відмова аудиту')
            return original(*args,**kwargs)
        monkeypatch.setattr(service,'audit',fail)
        with pytest.raises(ValueError):decide(db,pid,injury,'not_needed','Причина')
        assert not db.get(Injury,injury).exam_not_needed and task(db,pid,injury).status=='OPEN'


def test_index_migration_preserves_data_backup_idempotence(factory,prepared):
    from app.database.migrate_injury_vlk import migrate
    path=factory.kw['bind'].url.database
    with factory() as db:
        injury=create(db,prepared[3],'injuries')
        db.execute(text('DROP INDEX one_injury_vlk_task'));db.commit()
    backup=migrate(path);assert backup.is_file() and migrate(path) is None
    with factory() as db:assert db.get(Injury,injury) is not None
    with sqlite3.connect(backup) as db:assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='one_injury_vlk_task'").fetchone()


def test_database_rejects_duplicate_vlk_task(factory,prepared):
    from sqlalchemy.exc import IntegrityError
    with factory() as db:
        injury=create(db,prepared[3],'injuries')
        with pytest.raises(IntegrityError):
            db.add(PersonnelTask(person_id=prepared[3],kind='injury_vlk',injury_id=injury,title='Дублікат'))
            db.commit()
        db.rollback()
        assert len([t for t in service.Repo.rows(db,'tasks',prepared[3]) if t.kind=='injury_vlk'])==1


def test_index_migration_ddl_rollback(factory,prepared,monkeypatch):
    from app.database import migrate_injury_vlk as migration
    path=factory.kw['bind'].url.database
    with factory() as db:db.execute(text('DROP INDEX one_injury_vlk_task'));db.commit()
    original=migration.install_index
    def fail(db):original(db);raise ValueError('Тестова відмова після DDL')
    monkeypatch.setattr(migration,'install_index',fail)
    with pytest.raises(ValueError):migration.migrate(path)
    with sqlite3.connect(path) as db:assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='one_injury_vlk_task'").fetchone()

"""Independent personnel facts. Documents retain their existing storage/audit."""
from datetime import date, datetime, UTC
from sqlalchemy import Date, DateTime, String, ForeignKey, CheckConstraint, Index, UniqueConstraint, JSON, event, text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base
from app.models.staff import SystemTimestamps

class Owned:
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'), index=True)
    id: Mapped[int] = mapped_column(primary_key=True)

class Injury(Owned, SystemTimestamps, Base):
    __tablename__ = 'person_injuries'
    occurred_on: Mapped[date | None] = mapped_column(Date)
    description: Mapped[str | None] = mapped_column(String(200))
    area: Mapped[str | None] = mapped_column(String(1000))
    circumstances: Mapped[str | None] = mapped_column(String(2000))
    certificate_number: Mapped[str | None] = mapped_column(String(150))
    certificate_on: Mapped[date | None] = mapped_column(Date)
    exam_not_needed: Mapped[bool] = mapped_column(default=False)

class MedicalExam(Owned, SystemTimestamps, Base):
    __tablename__ = 'person_medical_exams'
    status: Mapped[str] = mapped_column(String(20), default='NEEDS_EXAM')
    basis: Mapped[str] = mapped_column(String(20), default='OTHER')
    basis_note: Mapped[str | None] = mapped_column(String(2000))
    injury_id: Mapped[int | None] = mapped_column(ForeignKey('person_injuries.id'))
    planned_on: Mapped[date | None] = mapped_column(Date)
    issued_on: Mapped[date | None] = mapped_column(Date)
    number: Mapped[str | None] = mapped_column(String(150))
    institution: Mapped[str | None] = mapped_column(String(1000))
    diagnosis: Mapped[str | None] = mapped_column(String(2000))
    fitness: Mapped[str | None] = mapped_column(String(20))
    __table_args__ = (CheckConstraint("status IN ('NEEDS_EXAM','PLANNED','COMPLETED')"), CheckConstraint("basis IN ('INJURY','ILLNESS','OTHER')"), CheckConstraint("fitness IS NULL OR fitness IN ('FIT','FIT_SUPPORT','UNFIT')"), CheckConstraint("injury_id IS NULL OR basis='INJURY'"))

class MedicalSelection(SystemTimestamps, Base):
    __tablename__ = 'person_medical_selections'
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'), primary_key=True)
    exam_id: Mapped[int | None] = mapped_column(ForeignKey('person_medical_exams.id'))

class Award(Owned, SystemTimestamps, Base):
    __tablename__ = 'person_awards'
    name: Mapped[str | None] = mapped_column(String(250))
    status: Mapped[str] = mapped_column(String(30), default='NOT_PROCESSED')
    injury_id: Mapped[int | None] = mapped_column(ForeignKey('person_injuries.id'))
    submission_on: Mapped[date | None] = mapped_column(Date)
    submission_number: Mapped[str | None] = mapped_column(String(150))
    submission_confirmed: Mapped[bool] = mapped_column(default=False)
    refusal_on: Mapped[date | None] = mapped_column(Date)
    refusal_number: Mapped[str | None] = mapped_column(String(150))
    refusal_reason: Mapped[str | None] = mapped_column(String(1000))
    refusal_confirmed: Mapped[bool] = mapped_column(default=False)
    awarded_on: Mapped[date | None] = mapped_column(Date)
    order_number: Mapped[str | None] = mapped_column(String(150))
    order_on: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (CheckConstraint("status IN ('NOT_PROCESSED','SUBMITTED','WAITING','AWARDED','NOT_APPROPRIATE')"), CheckConstraint('submission_confirmed=0 OR (submission_on IS NOT NULL AND coalesce(length(trim(submission_number)),0)>0)'), CheckConstraint('refusal_confirmed=0 OR (refusal_on IS NOT NULL AND coalesce(length(trim(refusal_number)),0)>0 AND coalesce(length(trim(refusal_reason)),0)>0)'))

class DnaSample(Owned, SystemTimestamps, Base):
    __tablename__ = 'person_dna_samples'
    envelope_number: Mapped[str | None] = mapped_column(String(150))
    collected_on: Mapped[date] = mapped_column(Date)
    storage_unit: Mapped[str | None] = mapped_column(String(250))

class PersonnelTask(Owned, SystemTimestamps, Base):
    __tablename__ = 'personnel_tasks'
    kind: Mapped[str] = mapped_column(String(100), default='manual')
    injury_id: Mapped[int | None] = mapped_column(ForeignKey('person_injuries.id'))
    award_id: Mapped[int | None] = mapped_column(ForeignKey('person_awards.id'))
    title: Mapped[str] = mapped_column(String(250))
    responsible: Mapped[str | None] = mapped_column(String(500))
    note: Mapped[str | None] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(String(20), default='OPEN')
    manual_decision: Mapped[bool] = mapped_column(default=False)
    decision_reason: Mapped[str | None] = mapped_column(String(1000))
    __table_args__ = (CheckConstraint("status IN ('OPEN','COMPLETED','CANCELLED')"), CheckConstraint("kind!='injury_award' OR injury_id IS NOT NULL"), Index('one_injury_award_task','injury_id',unique=True,sqlite_where=text("kind='injury_award'")))

class MedicalDocumentLink(SystemTimestamps, Base):
    __tablename__ = 'medical_document_links'
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('person_documents.id'), index=True)
    exam_id: Mapped[int | None] = mapped_column(ForeignKey('person_medical_exams.id'))
    injury_id: Mapped[int | None] = mapped_column(ForeignKey('person_injuries.id'))
    award_id: Mapped[int | None] = mapped_column(ForeignKey('person_awards.id'))
    category: Mapped[str] = mapped_column(String(50))
    __table_args__ = (CheckConstraint('(exam_id IS NOT NULL)+(injury_id IS NOT NULL)+(award_id IS NOT NULL)=1'), UniqueConstraint('document_id','exam_id','category'), UniqueConstraint('document_id','injury_id','category'), UniqueConstraint('document_id','award_id','category'))

class PersonnelAudit(Base):
    __tablename__ = 'personnel_audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'), index=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    entity: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[int] = mapped_column()
    operation: Mapped[str] = mapped_column(String(50))
    changes: Mapped[dict] = mapped_column(JSON)

MODELS = {'exams':MedicalExam,'injuries':Injury,'awards':Award,'dna':DnaSample,'tasks':PersonnelTask}
NEW_TABLE_NAMES = {m.__tablename__ for m in (*MODELS.values(),MedicalSelection,MedicalDocumentLink,PersonnelAudit)}
GUARDS = {'personnel_audit_no_update','personnel_audit_no_delete'} | {f'medical_{name}_{op}' for name in ('exam_owner','award_owner','task_owner','selection','link') for op in ('insert','update')}

def install_guards(connection):
    checks = {
      'exam_owner': ('person_medical_exams', "NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries i WHERE i.id=NEW.injury_id AND i.person_id=NEW.person_id)"),
      'award_owner': ('person_awards', "NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries i WHERE i.id=NEW.injury_id AND i.person_id=NEW.person_id)"),
      'task_owner': ('personnel_tasks', "(NEW.injury_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_injuries i WHERE i.id=NEW.injury_id AND i.person_id=NEW.person_id)) OR (NEW.award_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_awards a WHERE a.id=NEW.award_id AND a.person_id=NEW.person_id))"),
      'selection': ('person_medical_selections', "NEW.exam_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM person_medical_exams e WHERE e.id=NEW.exam_id AND e.person_id=NEW.person_id AND e.status='COMPLETED')"),
      'link': ('medical_document_links', ' OR '.join(f"(NEW.{fk} IS NOT NULL AND NOT EXISTS (SELECT 1 FROM {table} r JOIN person_documents d ON d.person_id=r.person_id WHERE r.id=NEW.{fk} AND d.id=NEW.document_id))" for fk,table in [('exam_id','person_medical_exams'),('injury_id','person_injuries'),('award_id','person_awards')])),
    }
    for name,(table,condition) in checks.items():
        for op in ('insert','update'):
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS medical_{name}_{op} BEFORE {op.upper()} ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT,'invalid medical owner or active selection'); END")
    for op in ('update','delete'):
        connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS personnel_audit_no_{op} BEFORE {op.upper()} ON personnel_audit BEGIN SELECT RAISE(ABORT,'personnel audit is append only'); END")

    for model in MODELS.values():
        checks=[]
        for col in model.__table__.columns:
            if isinstance(col.type,Date) and not isinstance(col.type,DateTime):
                checks.append(f"(NEW.{col.name} IS NOT NULL AND (length(NEW.{col.name})!=10 OR NEW.{col.name}<'0001-01-01' OR date(NEW.{col.name},'+0 days') IS NULL OR date(NEW.{col.name},'+0 days')!=NEW.{col.name}))")
            if isinstance(col.type,String) and col.type.length:checks.append(f"length(NEW.{col.name})>{col.type.length}")
        for op in ('insert','update'):
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS medical_values_{model.__tablename__}_{op} BEFORE {op.upper()} ON {model.__tablename__} WHEN {' OR '.join(checks)} BEGIN SELECT RAISE(ABORT,'invalid calendar date or text length'); END")
    connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS medical_selected_exam_update BEFORE UPDATE ON person_medical_exams WHEN NEW.status!='COMPLETED' AND EXISTS (SELECT 1 FROM person_medical_selections s WHERE s.exam_id=NEW.id) BEGIN SELECT RAISE(ABORT,'clear manual selection first'); END")

@event.listens_for(Base.metadata,'after_create')
def _guards(target,connection,**kwargs):
    from sqlalchemy import inspect
    if connection.dialect.name=='sqlite' and NEW_TABLE_NAMES <= set(inspect(connection).get_table_names()):install_guards(connection)

# ORM Date validation supplements the API's strict ISO date parsing.
for model in MODELS.values():
    def validate_dates(mapper,connection,target):
        for column in target.__table__.columns:
            if isinstance(column.type,Date) and not isinstance(column.type,DateTime):
                value=getattr(target,column.name)
                if value is not None and type(value) is not date:raise ValueError('Потрібна повна календарна дата.')
    event.listen(model,'before_insert',validate_dates);event.listen(model,'before_update',validate_dates)


GUARDS |= {f'medical_values_{m.__tablename__}_{op}' for m in MODELS.values() for op in ('insert','update')} | {'medical_selected_exam_update'}

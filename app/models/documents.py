"""Document lifecycle, independent presence, copies and append-only audit."""
from datetime import datetime, UTC
from sqlalchemy import String, Integer, JSON, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, Index, text, event
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base
from app.models.staff import SystemTimestamps

NEW_TABLE_NAMES = {'users', 'user_sessions', 'document_types', 'person_document_states', 'person_documents',
                   'document_details', 'document_driving_categories', 'document_files', 'document_audit'}
GUARD_NAMES = {'document_presence_insert','document_presence_update','document_details_source_insert','document_details_source_update',
               'document_audit_no_update','document_audit_no_delete','document_owner_insert','document_owner_update', 'document_type_presence'}


class DocumentType(SystemTimestamps, Base):
    __tablename__ = 'document_types'
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    is_primary: Mapped[bool] = mapped_column()
    schema_key: Mapped[str] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (CheckConstraint("code NOT IN ('passport','tax_number','military','birth_certificate') OR is_primary=1"),)


class PersonDocumentState(SystemTimestamps, Base):
    __tablename__ = 'person_document_states'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'))
    document_type_id: Mapped[int] = mapped_column(ForeignKey('document_types.id'))
    presence: Mapped[str] = mapped_column(String(20), default='UNKNOWN')
    __table_args__ = (UniqueConstraint('person_id', 'document_type_id'),
                     CheckConstraint("presence IN ('PRESENT','NEVER_OBTAINED','UNKNOWN')"))


class PersonDocument(SystemTimestamps, Base):
    __tablename__ = 'person_documents'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'), index=True)
    document_type_id: Mapped[int] = mapped_column(ForeignKey('document_types.id'), index=True)
    is_current: Mapped[bool] = mapped_column(default=True)
    passport_id: Mapped[int | None] = mapped_column(ForeignKey('passports.passport_id'), unique=True)
    replaces_id: Mapped[int | None] = mapped_column(ForeignKey('person_documents.id'), unique=True)
    override_status: Mapped[str | None] = mapped_column(String(30))
    override_reason: Mapped[str | None] = mapped_column(String(1000))
    override_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    override_fingerprint: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        CheckConstraint('is_current IN (0,1)'),
        CheckConstraint("override_status IS NULL OR override_status IN ('NOT_FILLED','PARTIALLY_FILLED','FILLED')"),
        CheckConstraint("override_status IS NULL OR (length(trim(override_reason)) > 0 AND override_user_id IS NOT NULL)"),
        Index('one_current_document', 'person_id', 'document_type_id', unique=True, sqlite_where=text('is_current=1')),
    )


class DocumentDetails(SystemTimestamps, Base):
    __tablename__ = 'document_details'
    document_id: Mapped[int] = mapped_column(ForeignKey('person_documents.id'), primary_key=True)
    series: Mapped[str | None] = mapped_column(String(100))
    number: Mapped[str | None] = mapped_column(String(100))
    issued_by: Mapped[str | None] = mapped_column(String(500))
    subtype: Mapped[str | None] = mapped_column(String(100))
    issued_day: Mapped[int | None] = mapped_column(Integer)
    issued_month: Mapped[int | None] = mapped_column(Integer)
    issued_year: Mapped[int | None] = mapped_column(Integer)
    expire_day: Mapped[int | None] = mapped_column(Integer)
    expire_month: Mapped[int | None] = mapped_column(Integer)
    expire_year: Mapped[int | None] = mapped_column(Integer)
    expiry_mode: Mapped[str] = mapped_column(String(20), default='unknown')
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (CheckConstraint("expiry_mode IN ('unknown','date','unlimited')"),)


class DrivingCategory(SystemTimestamps, Base):
    __tablename__ = 'document_driving_categories'
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('person_documents.id'), index=True)
    category: Mapped[str] = mapped_column(String(10))
    start_day: Mapped[int | None] = mapped_column(Integer)
    start_month: Mapped[int | None] = mapped_column(Integer)
    start_year: Mapped[int | None] = mapped_column(Integer)
    expire_day: Mapped[int | None] = mapped_column(Integer)
    expire_month: Mapped[int | None] = mapped_column(Integer)
    expire_year: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint('document_id', 'category'),)


class DocumentFile(SystemTimestamps, Base):
    __tablename__ = 'document_files'
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey('person_documents.id'), index=True)
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    original_name: Mapped[str] = mapped_column(String(250))
    content_type: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    side: Mapped[str] = mapped_column(String(20))
    is_removed: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (CheckConstraint("side IN ('front','back','page','other')"), CheckConstraint('size > 0'))


class DocumentAudit(Base):
    __tablename__ = 'document_audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'), index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey('person_documents.id'), index=True)
    document_type_id: Mapped[int] = mapped_column(ForeignKey('document_types.id'))
    file_id: Mapped[int | None] = mapped_column(ForeignKey('document_files.id'))
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    actor_kind: Mapped[str] = mapped_column(String(20), default='user')
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    operation: Mapped[str] = mapped_column(String(50))
    changes: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(1000))
    __table_args__ = (CheckConstraint("(actor_kind='user' AND actor_id IS NOT NULL) OR (actor_kind='migration' AND actor_id IS NULL)"),)


@event.listens_for(DocumentType.__table__,'after_create')
def _seed_catalog(target,connection,**kwargs):
    from app.document_schemas import SCHEMAS
    connection.execute(target.insert(),[{'code':code,'name':name,'is_primary':primary,'schema_key':code,'is_active':True}
        for code,(name,primary,_) in SCHEMAS.items()])


def install_guards(connection):
    for action in ('INSERT', 'UPDATE'):
        connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS document_owner_{action.lower()}
        BEFORE {action} ON person_documents WHEN
        (NEW.passport_id IS NOT NULL AND ((SELECT code FROM document_types WHERE id=NEW.document_type_id)!='passport'
        OR NOT EXISTS (SELECT 1 FROM passports p WHERE p.passport_id=NEW.passport_id AND p.person_id=NEW.person_id)))
        OR (NEW.replaces_id IS NOT NULL AND (NEW.replaces_id=NEW.id OR NOT EXISTS
        (SELECT 1 FROM person_documents d WHERE d.id=NEW.replaces_id AND d.person_id=NEW.person_id AND d.document_type_id=NEW.document_type_id)))
        BEGIN SELECT RAISE(ABORT,'document source or replacement belongs to another person/type'); END""")
        connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS document_presence_{action.lower()}
        BEFORE {action} ON person_document_states WHEN NEW.presence='NEVER_OBTAINED'
        AND (SELECT is_primary FROM document_types WHERE id=NEW.document_type_id)=1
        BEGIN SELECT RAISE(ABORT,'primary document cannot be never obtained'); END""")
        connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS document_details_source_{action.lower()}
        BEFORE {action} ON document_details WHEN EXISTS (SELECT 1 FROM person_documents d JOIN document_types t
        ON t.id=d.document_type_id WHERE d.id=NEW.document_id AND t.code IN ('passport','tax_number'))
        BEGIN SELECT RAISE(ABORT,'use canonical passport or person tax number'); END""")
    for action in ('UPDATE', 'DELETE'):
        connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS document_audit_no_{action.lower()}
        BEFORE {action} ON document_audit BEGIN SELECT RAISE(ABORT,'document audit is append only'); END""")
    connection.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS document_type_presence BEFORE UPDATE ON document_types
    WHEN NEW.is_primary=1 AND EXISTS (SELECT 1 FROM person_document_states s WHERE s.document_type_id=NEW.id AND s.presence='NEVER_OBTAINED')
    BEGIN SELECT RAISE(ABORT,'primary document cannot be never obtained'); END""")


@event.listens_for(DocumentAudit.__table__, 'after_create')
def _guards(target, connection, **kwargs):
    if connection.dialect.name == 'sqlite':
        install_guards(connection)


def _validate_components(mapper, connection, target):
    from app.utils.date_utils import validate_date_components
    for prefix in (('issued','expire') if isinstance(target,DocumentDetails) else ('start','expire')):
        parts=validate_date_components(*(getattr(target,prefix+'_'+p) for p in ('day','month','year')),max_year=9999)
        if any(v is not None for v in (parts.day,parts.month,parts.year)) and parts.as_date() is None:
            raise ValueError('Для цього поля потрібна повна календарна дата.')


for _model in (DocumentDetails,DrivingCategory):
    event.listen(_model,'before_insert',_validate_components)
    event.listen(_model,'before_update',_validate_components)

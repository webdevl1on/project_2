"""Audit only the domain operations not already covered by a dedicated journal."""
from datetime import datetime,UTC
from sqlalchemy import String,Integer,DateTime,ForeignKey,JSON,CheckConstraint,Index,event,inspect
from sqlalchemy.orm import Mapped,mapped_column
from app.database.base import Base


class SubjectAudit(Base):
    __tablename__='subject_audit'
    id:Mapped[int]=mapped_column(primary_key=True)
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(UTC))
    actor_user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id'))
    person_id:Mapped[int|None]=mapped_column(ForeignKey('persons.person_id'))
    object_type:Mapped[str]=mapped_column(String(80))
    object_id:Mapped[int]=mapped_column(Integer)
    category:Mapped[str]=mapped_column(String(40))
    operation:Mapped[str]=mapped_column(String(30))
    before:Mapped[dict]=mapped_column(JSON)
    after:Mapped[dict]=mapped_column(JSON)
    reason:Mapped[str|None]=mapped_column(String(2000))
    __table_args__=(CheckConstraint("operation IN ('create','edit','delete')",name='subject_audit_operation'),
                   Index('subject_audit_person_time','person_id','occurred_at'),)


@event.listens_for(SubjectAudit.__table__,'after_create')
def guards(table,connection,**kw):
    if connection.dialect.name=='sqlite':
        for action in ('UPDATE','DELETE'):
            connection.exec_driver_sql(f"CREATE TRIGGER subject_audit_no_{action.lower()} BEFORE {action} ON subject_audit BEGIN SELECT RAISE(ABORT,'subject audit is append only'); END")

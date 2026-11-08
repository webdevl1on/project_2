"""Rules, independent sources, fixed temporary grants and append-only ACL audit."""
from datetime import datetime,UTC
from sqlalchemy import String,Integer,DateTime,ForeignKey,Boolean,JSON,CheckConstraint,Index,text,event,inspect
from sqlalchemy.orm import Mapped,mapped_column
from app.database.base import Base
from app.models.staff import SystemTimestamps

class AccessTemplate(SystemTimestamps,Base):
    __tablename__='access_templates'
    id:Mapped[int]=mapped_column(primary_key=True)
    name:Mapped[str]=mapped_column(String(200))
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)

class TemplateAssignment(SystemTimestamps,Base):
    __tablename__='access_template_assignments'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    template_id:Mapped[int]=mapped_column(ForeignKey('access_templates.id'))
    unit_id:Mapped[int]=mapped_column(ForeignKey('org_units.id'))
    starts_at:Mapped[datetime|None]=mapped_column(DateTime)
    ends_at:Mapped[datetime|None]=mapped_column(DateTime)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)
    __table_args__=(CheckConstraint('starts_at IS NULL OR ends_at IS NULL OR ends_at>starts_at',name='access_template_period'),)

class PositionAccessPolicy(SystemTimestamps,Base):
    __tablename__='position_access_policies'
    id:Mapped[int]=mapped_column(primary_key=True)
    position_id:Mapped[int]=mapped_column(ForeignKey('positions.position_id'),unique=True)
    is_active:Mapped[bool]=mapped_column(Boolean,default=True)

class TemporaryAccess(SystemTimestamps,Base):
    __tablename__='temporary_access'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    position_id:Mapped[int]=mapped_column(ForeignKey('positions.position_id'))
    unit_id:Mapped[int]=mapped_column(ForeignKey('org_units.id'))
    starts_at:Mapped[datetime]=mapped_column(DateTime)
    ends_at:Mapped[datetime]=mapped_column(DateTime)
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime)
    __table_args__=(CheckConstraint('ends_at>starts_at',name='temporary_access_period'),)

class AccessRule(SystemTimestamps,Base):
    __tablename__='access_rules'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id'),index=True)
    template_id:Mapped[int|None]=mapped_column(ForeignKey('access_templates.id'),index=True)
    policy_id:Mapped[int|None]=mapped_column(ForeignKey('position_access_policies.id'),index=True)
    temporary_id:Mapped[int|None]=mapped_column(ForeignKey('temporary_access.id'),index=True)
    scope_type:Mapped[str]=mapped_column(String(20))
    unit_id:Mapped[int|None]=mapped_column(ForeignKey('org_units.id'))
    position_id:Mapped[int|None]=mapped_column(ForeignKey('positions.position_id'))
    person_id:Mapped[int|None]=mapped_column(ForeignKey('persons.person_id'))
    category:Mapped[str]=mapped_column(String(40))
    action:Mapped[str]=mapped_column(String(30))
    effect:Mapped[str]=mapped_column(String(5))
    starts_at:Mapped[datetime|None]=mapped_column(DateTime)
    ends_at:Mapped[datetime|None]=mapped_column(DateTime)
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime)
    created_by:Mapped[int]=mapped_column(ForeignKey('users.id'))
    __table_args__=(
        CheckConstraint("effect IN ('ALLOW','DENY')",name='access_rule_effect'),
        CheckConstraint('(CASE WHEN user_id IS NULL THEN 0 ELSE 1 END + CASE WHEN template_id IS NULL THEN 0 ELSE 1 END + CASE WHEN policy_id IS NULL THEN 0 ELSE 1 END + CASE WHEN temporary_id IS NULL THEN 0 ELSE 1 END)=1',name='access_rule_source'),
        CheckConstraint("(scope_type IN ('global','relative') AND unit_id IS NULL AND position_id IS NULL AND person_id IS NULL) OR (scope_type='unit' AND unit_id IS NOT NULL AND position_id IS NULL AND person_id IS NULL) OR (scope_type='position' AND position_id IS NOT NULL AND unit_id IS NULL AND person_id IS NULL) OR (scope_type='person' AND person_id IS NOT NULL AND unit_id IS NULL AND position_id IS NULL)",name='access_rule_scope'),
        CheckConstraint("(scope_type='relative')=(template_id IS NOT NULL OR policy_id IS NOT NULL)",name='access_rule_relative'),
        CheckConstraint('starts_at IS NULL OR ends_at IS NULL OR ends_at>starts_at',name='access_rule_period'),)

class AccessDelegation(SystemTimestamps,Base):
    __tablename__='access_delegations'
    id:Mapped[int]=mapped_column(primary_key=True)
    delegator_id:Mapped[int]=mapped_column(ForeignKey('users.id'))
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    unit_id:Mapped[int]=mapped_column(ForeignKey('org_units.id'))
    capabilities:Mapped[list]=mapped_column(JSON)
    starts_at:Mapped[datetime]=mapped_column(DateTime)
    ends_at:Mapped[datetime]=mapped_column(DateTime)
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime)
    __table_args__=(CheckConstraint('ends_at>starts_at',name='access_delegation_period'),CheckConstraint('delegator_id!=user_id',name='access_delegation_not_self'))

class AccessReview(SystemTimestamps,Base):
    __tablename__='access_reviews'
    id:Mapped[int]=mapped_column(primary_key=True)
    user_id:Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    status:Mapped[str]=mapped_column(String(10),default='OPEN')
    reason:Mapped[str]=mapped_column(String(2000))
    decision:Mapped[str|None]=mapped_column(String(2000))
    decided_by:Mapped[int|None]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint("status IN ('OPEN','RESOLVED')",name='access_review_status'),
        Index('one_open_access_review','user_id',unique=True,sqlite_where=text("status='OPEN'"),postgresql_where=text("status='OPEN'")),)

class AccessAudit(Base):
    __tablename__='access_audit'
    id:Mapped[int]=mapped_column(primary_key=True)
    actor_user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id'))
    target_user_id:Mapped[int|None]=mapped_column(ForeignKey('users.id'),index=True)
    occurred_at:Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(UTC))
    operation:Mapped[str]=mapped_column(String(40))
    before:Mapped[dict]=mapped_column(JSON,default=dict)
    after:Mapped[dict]=mapped_column(JSON,default=dict)
    reason:Mapped[str]=mapped_column(String(2000))
    __table_args__=(CheckConstraint('length(trim(reason)) BETWEEN 1 AND 2000',name='access_audit_reason'),)

@event.listens_for(Base.metadata,'after_create')
def access_guards(metadata,connection,**kw):
    if connection.dialect.name!='sqlite':return
    tables=set(inspect(connection).get_table_names())
    for action in ('UPDATE','DELETE'):
        if 'access_audit' in tables:connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS access_audit_no_{action.lower()} BEFORE {action} ON access_audit BEGIN SELECT RAISE(ABORT,'access audit is append only'); END")
    for table in ('access_rules','access_templates','access_template_assignments','position_access_policies','temporary_access','access_delegations','access_reviews'):
        if table in tables:connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'access history cannot be deleted'); END")

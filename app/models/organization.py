"""Stable organizational identity; names and primary/operational command are dated."""
from datetime import date,datetime,UTC
from sqlalchemy import String,Integer,Date,DateTime,ForeignKey,JSON,CheckConstraint,Index,event,inspect
from sqlalchemy.orm import Mapped,mapped_column,validates
from app.database.base import Base
from app.models.staff import SystemTimestamps,exact_date

KIND_LABELS={'unit':'Військова частина','regiment':'Полк','battalion':'Батальйон','detachment':'Загін','company':'Рота','battery':'Батарея','platoon':'Взвод','squad':'Відділення','team':'Розрахунок','crew':'Екіпаж','other':'Інший підрозділ'}
KINDS=tuple(KIND_LABELS)
KIND_LEVELS={'unit':1,'regiment':2,'battalion':3,'detachment':3,'company':4,'battery':4,'platoon':5,'squad':6,'team':7,'crew':7}
ROSTER_KINDS=frozenset({'unit','regiment','battalion','detachment','company','battery'})

def level_of(unit):
    return unit.hierarchy_level if unit.kind=='other' else KIND_LEVELS[unit.kind]


class OrgUnit(SystemTimestamps,Base):
    __tablename__='org_units'
    id: Mapped[int]=mapped_column(primary_key=True)
    kind: Mapped[str]=mapped_column(String(20))
    hierarchy_level: Mapped[int|None]=mapped_column(Integer)
    formed_on: Mapped[date]=mapped_column(Date)
    dissolved_on: Mapped[date|None]=mapped_column(Date)
    sort_order: Mapped[int]=mapped_column(Integer,default=0)
    annulled_at: Mapped[datetime|None]=mapped_column(DateTime)
    annulment_reason: Mapped[str|None]=mapped_column(String(2000))
    annulled_by: Mapped[int|None]=mapped_column(ForeignKey('users.id'))
    __table_args__=(CheckConstraint('kind IN ('+','.join("'"+kind+"'" for kind in KINDS)+')',name='org_unit_kind'),
                   CheckConstraint("(kind='other' AND (hierarchy_level IS NULL OR hierarchy_level BETWEEN 1 AND 7)) OR (kind!='other' AND hierarchy_level IS NULL)",name='org_unit_level'),
                   CheckConstraint('dissolved_on IS NULL OR dissolved_on>=formed_on',name='org_unit_lifetime'),
                   CheckConstraint("(annulled_at IS NULL AND annulment_reason IS NULL AND annulled_by IS NULL) OR (annulled_at IS NOT NULL AND annulment_reason IS NOT NULL AND length(trim(annulment_reason)) BETWEEN 1 AND 2000)",name='org_unit_annulment'))
    @validates('formed_on','dissolved_on')
    def validate_date(self,key,value):return exact_date(value,key=='formed_on')

class OrgUnitState(SystemTimestamps,Base):
    __tablename__='org_unit_states'
    id: Mapped[int]=mapped_column(primary_key=True)
    org_unit_id: Mapped[int]=mapped_column(ForeignKey('org_units.id'),index=True)
    name: Mapped[str]=mapped_column(String(500))
    normalized_name: Mapped[str]=mapped_column(String(500))
    primary_parent_id: Mapped[int|None]=mapped_column(ForeignKey('org_units.id'),index=True)
    valid_from: Mapped[date]=mapped_column(Date)
    valid_to: Mapped[date|None]=mapped_column(Date)
    __table_args__=(CheckConstraint('valid_to IS NULL OR valid_to>=valid_from',name='org_state_period'),
                   CheckConstraint('primary_parent_id IS NULL OR primary_parent_id!=org_unit_id',name='org_state_not_self'),
                   CheckConstraint('length(trim(normalized_name))>0',name='org_state_name'),
                   Index('ix_org_state_period','org_unit_id','valid_from','valid_to'))
    @validates('valid_from','valid_to')
    def validate_date(self,key,value):return exact_date(value,key=='valid_from')

class OperationalSubordination(SystemTimestamps,Base):
    __tablename__='org_operational_subordinations'
    id: Mapped[int]=mapped_column(primary_key=True)
    org_unit_id: Mapped[int]=mapped_column(ForeignKey('org_units.id'),index=True)
    parent_id: Mapped[int]=mapped_column(ForeignKey('org_units.id'),index=True)
    valid_from: Mapped[date]=mapped_column(Date)
    valid_to: Mapped[date|None]=mapped_column(Date)
    note: Mapped[str|None]=mapped_column(String(2000))
    __table_args__=(CheckConstraint('valid_to IS NULL OR valid_to>=valid_from',name='org_operational_period'),
                   CheckConstraint('parent_id!=org_unit_id',name='org_operational_not_self'),)
    @validates('valid_from','valid_to')
    def validate_date(self,key,value):return exact_date(value,key=='valid_from')

class OrgAudit(Base):
    __tablename__='org_audit'
    id: Mapped[int]=mapped_column(primary_key=True)
    org_unit_id: Mapped[int]=mapped_column(ForeignKey('org_units.id'),index=True)
    actor_user_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime]=mapped_column(DateTime,default=lambda:datetime.now(UTC))
    operation: Mapped[str]=mapped_column(String(30))
    before: Mapped[dict]=mapped_column(JSON)
    after: Mapped[dict]=mapped_column(JSON)
    reason: Mapped[str|None]=mapped_column(String(2000))
    __table_args__=(CheckConstraint("operation IN ('create','state','dissolve','annul','order','operational','coverage','map','import','withdraw','position','position_annul','reassignment')",name='org_audit_operation'),)

@event.listens_for(Base.metadata,'after_create')
def organization_guards(metadata,connection,**kwargs):
    if connection.dialect.name!='sqlite':return
    tables=set(inspect(connection).get_table_names())
    for table in ('org_units','org_unit_states','org_operational_subordinations'):
        if table in tables:
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'organizational history cannot be deleted'); END")
    if 'org_units' in tables:
        connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS org_unit_id_immutable BEFORE UPDATE OF id ON org_units WHEN NEW.id!=OLD.id BEGIN SELECT RAISE(ABORT,'organizational identity is immutable'); END")
    if 'org_audit' in tables:
        for operation in ('UPDATE','DELETE'):
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS org_audit_no_{operation.lower()} BEFORE {operation} ON org_audit BEGIN SELECT RAISE(ABORT,'organization audit is append only'); END")
    if 'org_unit_states' in tables:
        for operation in ('INSERT','UPDATE'):
            connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS org_state_period_{operation.lower()} BEFORE {operation} ON org_unit_states
                WHEN EXISTS (SELECT 1 FROM org_unit_states s WHERE s.id!=NEW.id AND s.org_unit_id=NEW.org_unit_id
                 AND s.valid_from<=coalesce(NEW.valid_to,'9999-12-31') AND NEW.valid_from<=coalesce(s.valid_to,'9999-12-31'))
                BEGIN SELECT RAISE(ABORT,'organization state periods overlap'); END""")

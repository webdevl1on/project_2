"""Explicit staffing coverage and import receipts; never a second assignment store."""
from datetime import date,datetime
from sqlalchemy import ForeignKey,Date,DateTime,String,Integer,JSON,UniqueConstraint,CheckConstraint,Index
from sqlalchemy.orm import Mapped,mapped_column
from app.database.base import Base
from app.models.staff import SystemTimestamps

class OrgCoverage(SystemTimestamps,Base):
    __tablename__='org_staff_coverage'
    id: Mapped[int]=mapped_column(primary_key=True)
    org_unit_id: Mapped[int]=mapped_column(ForeignKey('org_units.id'),index=True)
    staff_version_id: Mapped[int]=mapped_column(ForeignKey('staff_versions.id'),index=True)
    valid_from: Mapped[date]=mapped_column(Date)
    valid_to: Mapped[date|None]=mapped_column(Date)
    annulled_at: Mapped[datetime|None]=mapped_column(DateTime)
    annulment_reason: Mapped[str|None]=mapped_column(String(2000))
    __table_args__=(CheckConstraint('valid_to IS NULL OR valid_to>=valid_from',name='org_coverage_period'),)

class OrgStaffImport(SystemTimestamps,Base):
    __tablename__='org_staff_imports'
    id: Mapped[int]=mapped_column(primary_key=True)
    identity_key: Mapped[str]=mapped_column(String(64),unique=True)
    scope_unit_id: Mapped[int]=mapped_column(ForeignKey('org_units.id'))
    owner_unit_id: Mapped[int]=mapped_column(ForeignKey('org_units.id'))
    staff_version_id: Mapped[int|None]=mapped_column(ForeignKey('staff_versions.id'))
    mode: Mapped[str]=mapped_column(String(20))
    effective_on: Mapped[date]=mapped_column(Date)
    valid_to: Mapped[date|None]=mapped_column(Date)
    actor_id: Mapped[int]=mapped_column(ForeignKey('users.id'))
    snapshot: Mapped[dict]=mapped_column(JSON)
    effects: Mapped[dict]=mapped_column(JSON,default=dict)
    withdrawn_at: Mapped[datetime|None]=mapped_column(DateTime)
    withdrawal_reason: Mapped[str|None]=mapped_column(String(2000))
    __table_args__=(CheckConstraint("mode IN ('add','official','correct','replace')",name='org_import_mode'),)

class OrgStaffImportRow(SystemTimestamps,Base):
    __tablename__='org_staff_import_rows'
    id: Mapped[int]=mapped_column(primary_key=True)
    import_id: Mapped[int]=mapped_column(ForeignKey('org_staff_imports.id'),index=True)
    row_number: Mapped[int]=mapped_column(Integer)
    payload: Mapped[dict]=mapped_column(JSON)
    status: Mapped[str]=mapped_column(String(20),default='pending')
    issue: Mapped[str|None]=mapped_column(String(2000))
    position_id: Mapped[int|None]=mapped_column(ForeignKey('positions.position_id'))
    before: Mapped[dict|None]=mapped_column(JSON)
    after_revision: Mapped[int|None]=mapped_column(Integer)
    __table_args__=(UniqueConstraint('import_id','row_number'),CheckConstraint("status IN ('pending','accepted','unchanged','conflict')",name='org_import_row_status'),)

class OrgReassignment(SystemTimestamps,Base):
    __tablename__='org_reassignments'
    id: Mapped[int]=mapped_column(primary_key=True)
    import_id: Mapped[int]=mapped_column(ForeignKey('org_staff_imports.id'))
    assignment_id: Mapped[int]=mapped_column(ForeignKey('person_assignments.id'))
    replacement_position_id: Mapped[int|None]=mapped_column(ForeignKey('positions.position_id'))
    resolved_assignment_id: Mapped[int|None]=mapped_column(ForeignKey('person_assignments.id'))
    __table_args__=(UniqueConstraint('import_id','assignment_id'),)

# SQLite mirrors the source/immutability guards for isolated tests and legacy tools.
from sqlalchemy import event,inspect
from app.models.reference_book import Position
@event.listens_for(Base.metadata,'after_create')
def organization_staff_guards(metadata,connection,**kwargs):
    if connection.dialect.name!='sqlite':return
    tables=set(inspect(connection).get_table_names())
    for table in ('org_staff_coverage','org_staff_imports','org_staff_import_rows','org_reassignments'):
        if table in tables:connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'organization staffing history cannot be deleted'); END")
    if 'positions' not in tables or 'org_staff_coverage' not in tables:return
    connection.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS org_position_links_immutable BEFORE UPDATE ON positions BEGIN
      SELECT CASE WHEN OLD.org_unit_id IS NOT NULL AND NEW.org_unit_id IS NOT OLD.org_unit_id THEN RAISE(ABORT,'historical position organization is immutable') END;
      SELECT CASE WHEN NEW.annulled_at IS NOT NULL AND EXISTS(SELECT 1 FROM person_assignments WHERE staff_position_id=OLD.position_id AND annulled_at IS NULL) THEN RAISE(ABORT,'position has nonannulled assignments') END;
      SELECT CASE WHEN EXISTS(SELECT 1 FROM person_assignments WHERE staff_position_id=OLD.position_id AND annulled_at IS NULL AND ((NEW.valid_from IS NOT NULL AND assigned_from<NEW.valid_from) OR (NEW.valid_to IS NOT NULL AND (assigned_to IS NULL OR assigned_to>NEW.valid_to)))) THEN RAISE(ABORT,'assignment outside position period') END;
    END""")
    connection.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS org_structure_link_immutable BEFORE UPDATE ON staff_structures WHEN OLD.org_unit_id IS NOT NULL AND NEW.org_unit_id IS NOT OLD.org_unit_id BEGIN SELECT RAISE(ABORT,'historical structure organization is immutable'); END""")
    for action in ('INSERT','UPDATE'):
        connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS org_coverage_{action.lower()} BEFORE {action} ON org_staff_coverage WHEN NEW.annulled_at IS NULL BEGIN
          SELECT CASE WHEN EXISTS(SELECT 1 FROM org_staff_coverage c WHERE c.id!=coalesce(NEW.id,-1) AND c.org_unit_id=NEW.org_unit_id AND c.annulled_at IS NULL AND c.valid_from<=coalesce(NEW.valid_to,'9999-12-31') AND NEW.valid_from<=coalesce(c.valid_to,'9999-12-31')) THEN RAISE(ABORT,'effective sources overlap') END;
          SELECT CASE WHEN NOT EXISTS(SELECT 1 FROM org_units u JOIN staff_versions v ON v.id=NEW.staff_version_id WHERE u.id=NEW.org_unit_id AND u.annulled_at IS NULL AND v.annulled_at IS NULL AND NEW.valid_from>=u.formed_on AND NEW.valid_from>=v.valid_from AND (u.dissolved_on IS NULL OR (NEW.valid_to IS NOT NULL AND NEW.valid_to<=u.dissolved_on)) AND (v.valid_to IS NULL OR (NEW.valid_to IS NOT NULL AND NEW.valid_to<=v.valid_to))) THEN RAISE(ABORT,'coverage outside source period') END;
        END""")
    connection.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS org_coverage_assignment_dependencies BEFORE UPDATE ON org_staff_coverage BEGIN
      SELECT CASE WHEN EXISTS(SELECT 1 FROM person_assignments a JOIN positions p ON p.position_id=a.staff_position_id WHERE p.org_unit_id=OLD.org_unit_id AND p.staff_version_id=OLD.staff_version_id AND a.annulled_at IS NULL
        AND NOT (NEW.annulled_at IS NULL AND NEW.org_unit_id=p.org_unit_id AND NEW.staff_version_id=p.staff_version_id AND NEW.valid_from<=a.assigned_from AND (NEW.valid_to IS NULL OR (a.assigned_to IS NOT NULL AND a.assigned_to<=NEW.valid_to)))
        AND NOT EXISTS(SELECT 1 FROM org_staff_coverage c WHERE c.id!=OLD.id AND c.org_unit_id=p.org_unit_id AND c.staff_version_id=p.staff_version_id AND c.annulled_at IS NULL AND c.valid_from<=a.assigned_from AND (c.valid_to IS NULL OR (a.assigned_to IS NOT NULL AND a.assigned_to<=c.valid_to))))
        THEN RAISE(ABORT,'assignment outside effective staffing source') END;
    END""")
    connection.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS org_version_dependencies BEFORE UPDATE ON staff_versions BEGIN
      SELECT CASE WHEN NEW.annulled_at IS NOT NULL AND EXISTS(SELECT 1 FROM positions WHERE staff_version_id=NEW.id AND annulled_at IS NULL) THEN RAISE(ABORT,'version has active positions') END;
      SELECT CASE WHEN EXISTS(SELECT 1 FROM org_staff_coverage WHERE staff_version_id=NEW.id AND annulled_at IS NULL AND (NEW.annulled_at IS NOT NULL OR valid_from<NEW.valid_from OR (NEW.valid_to IS NOT NULL AND (valid_to IS NULL OR valid_to>NEW.valid_to)))) THEN RAISE(ABORT,'coverage outside version period') END;
    END""")
    connection.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS org_unit_staff_dependencies BEFORE UPDATE ON org_units BEGIN
      SELECT CASE WHEN NEW.kind NOT IN ('unit','regiment','battalion','company') AND EXISTS(SELECT 1 FROM staff_structures WHERE org_unit_id=NEW.id) THEN RAISE(ABORT,'independent staff owner must be company or higher') END;
      SELECT CASE WHEN NEW.annulled_at IS NOT NULL AND EXISTS(SELECT 1 FROM positions WHERE (org_unit_id=NEW.id OR managed_unit_id=NEW.id) AND annulled_at IS NULL) THEN RAISE(ABORT,'organization has staffing dependencies') END;
      SELECT CASE WHEN EXISTS(SELECT 1 FROM org_staff_coverage WHERE org_unit_id=NEW.id AND annulled_at IS NULL AND (NEW.annulled_at IS NOT NULL OR valid_from<NEW.formed_on OR (NEW.dissolved_on IS NOT NULL AND (valid_to IS NULL OR valid_to>NEW.dissolved_on)))) THEN RAISE(ABORT,'coverage outside organization lifetime') END;
    END""")
    for action in ('INSERT','UPDATE'):
        connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS org_structure_owner_{action.lower()} BEFORE {action} ON staff_structures WHEN NEW.org_unit_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM org_units WHERE id=NEW.org_unit_id AND annulled_at IS NULL AND kind IN ('unit','regiment','battalion','company')) BEGIN SELECT RAISE(ABORT,'independent staff owner must be company or higher'); END""")
        connection.exec_driver_sql(f"""CREATE TRIGGER IF NOT EXISTS org_assignment_source_{action.lower()} BEFORE {action} ON person_assignments WHEN NEW.annulled_at IS NULL BEGIN
          SELECT CASE WHEN EXISTS(SELECT 1 FROM positions p WHERE p.position_id=NEW.staff_position_id AND (p.annulled_at IS NOT NULL OR (p.valid_from IS NOT NULL AND NEW.assigned_from<p.valid_from) OR (p.valid_to IS NOT NULL AND (NEW.assigned_to IS NULL OR NEW.assigned_to>p.valid_to)))) THEN RAISE(ABORT,'assignment outside position period') END;
          SELECT CASE WHEN EXISTS(SELECT 1 FROM positions p WHERE p.position_id=NEW.staff_position_id AND p.org_unit_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM org_staff_coverage c JOIN org_units u ON u.id=c.org_unit_id WHERE c.org_unit_id=p.org_unit_id AND c.staff_version_id=p.staff_version_id AND c.annulled_at IS NULL AND u.annulled_at IS NULL AND NEW.assigned_from>=u.formed_on AND (u.dissolved_on IS NULL OR (NEW.assigned_to IS NOT NULL AND NEW.assigned_to<=u.dissolved_on)) AND c.valid_from<=NEW.assigned_from AND (c.valid_to IS NULL OR (NEW.assigned_to IS NOT NULL AND NEW.assigned_to<=c.valid_to)))) THEN RAISE(ABORT,'assignment outside effective staffing source') END;
        END""")

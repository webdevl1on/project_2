"""Effective-dated staff and assignments. No physical current-state table."""
from datetime import date, datetime, UTC
from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, CheckConstraint, UniqueConstraint, Index, event
from sqlalchemy.orm import Mapped, mapped_column, relationship, declared_attr, validates, synonym
from app.database.base import Base


def exact_date(value, required=True):
    if value is None and not required:
        return None
    if type(value) is not date:
        raise ValueError("Потрібна повна календарна дата.")
    return value


class SystemTimestamps:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    @declared_attr.directive
    def __mapper_args__(cls):
        return {"version_id_col": cls.revision}


class StaffStructure(SystemTimestamps, Base):
    __tablename__ = "staff_structures"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    versions: Mapped[list["StaffVersion"]] = relationship(back_populates="structure")


class StaffVersion(SystemTimestamps, Base):
    __tablename__ = "staff_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    staff_structure_id: Mapped[int] = mapped_column(ForeignKey("staff_structures.id"), index=True)
    name: Mapped[str] = mapped_column(String)
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    import_key: Mapped[str | None] = mapped_column(String, unique=True)
    structure: Mapped[StaffStructure] = relationship(back_populates="versions")
    positions: Mapped[list["Position"]] = relationship(back_populates="staff_version")
    __table_args__ = (CheckConstraint("valid_to IS NULL OR valid_to >= valid_from"),
                      UniqueConstraint("staff_structure_id", "name"))

    @validates("valid_from", "valid_to")
    def validate_date(self, key, value):
        return exact_date(value, key == "valid_from")


class PersonAssignment(SystemTimestamps, Base):
    __tablename__ = "person_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.person_id"), index=True)
    staff_position_id: Mapped[int] = mapped_column(ForeignKey("positions.position_id"), index=True)
    assigned_from: Mapped[date] = mapped_column(Date)
    assigned_to: Mapped[date | None] = mapped_column(Date)
    person: Mapped["Person"] = relationship(back_populates="positions")
    position: Mapped["Position"] = relationship(back_populates="persons")
    # Read/constructor compatibility only; these are aliases of the SAME history row.
    person_position_id = synonym("id")
    position_id = synonym("staff_position_id")
    __table_args__ = (CheckConstraint("assigned_to IS NULL OR assigned_to >= assigned_from"),
                      Index("ix_assignment_person_period", "person_id", "assigned_from", "assigned_to"),
                      Index("ix_assignment_position_period", "staff_position_id", "assigned_from", "assigned_to"))

    @validates("assigned_from", "assigned_to")
    def validate_date(self, key, value):
        return exact_date(value, key == "assigned_from")


# DB guards cover writes outside the services, including competing connections.
_VERSION_GUARD = """
 SELECT CASE WHEN EXISTS (
   SELECT 1 FROM staff_versions v WHERE v.id != NEW.id
   AND v.staff_structure_id=NEW.staff_structure_id
   AND v.valid_from<=coalesce(NEW.valid_to,'9999-12-31')
   AND NEW.valid_from<=coalesce(v.valid_to,'9999-12-31')
 ) THEN RAISE(ABORT,'staff version periods overlap') END;
 SELECT CASE WHEN EXISTS (
   SELECT 1 FROM person_assignments a JOIN positions p ON p.position_id=a.staff_position_id
   WHERE p.staff_version_id=NEW.id AND (a.assigned_from<NEW.valid_from OR
     (NEW.valid_to IS NOT NULL AND (a.assigned_to IS NULL OR a.assigned_to>NEW.valid_to)))
 ) THEN RAISE(ABORT,'assignments outside version period') END;
"""
_ASSIGNMENT_GUARD = """
 SELECT CASE WHEN NOT EXISTS (
   SELECT 1 FROM positions p JOIN staff_versions v ON v.id=p.staff_version_id
   WHERE p.position_id=NEW.staff_position_id AND NEW.assigned_from>=v.valid_from
   AND (v.valid_to IS NULL OR (NEW.assigned_to IS NOT NULL AND NEW.assigned_to<=v.valid_to))
 ) THEN RAISE(ABORT,'assignment outside version period') END;
 SELECT CASE WHEN EXISTS (
   SELECT 1 FROM person_assignments a WHERE a.id != NEW.id
   AND (a.person_id=NEW.person_id OR a.staff_position_id=NEW.staff_position_id)
   AND a.assigned_from<=coalesce(NEW.assigned_to,'9999-12-31')
   AND NEW.assigned_from<=coalesce(a.assigned_to,'9999-12-31')
 ) THEN RAISE(ABORT,'assignment periods overlap') END;
"""


@event.listens_for(Base.metadata, "after_create")
def install_staff_guards(metadata, connection, **kwargs):
    if connection.dialect.name != "sqlite":
        return
    for table, guard in (("staff_versions", _VERSION_GUARD), ("person_assignments", _ASSIGNMENT_GUARD)):
        for action in ("INSERT", "UPDATE"):
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS guard_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN {guard} END")
        connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS guard_{table}_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'historical records cannot be deleted'); END")
    connection.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS guard_position_version BEFORE UPDATE OF staff_version_id ON positions
      WHEN OLD.staff_version_id != NEW.staff_version_id BEGIN SELECT RAISE(ABORT,'position version is immutable'); END""")
    connection.exec_driver_sql("""CREATE TRIGGER IF NOT EXISTS guard_position_delete BEFORE DELETE ON positions
      BEGIN SELECT RAISE(ABORT,'historical positions cannot be deleted'); END""")
    for table, fields in (("staff_versions", (("valid_from",True),("valid_to",False))),
                          ("person_assignments", (("assigned_from",True),("assigned_to",False))),
                          ("person_events", (("date_start",True),("date_end",False),("order_date",False)))):
        checks=[]
        for field,required in fields:
            invalid=f"(length(NEW.{field}) != 10 OR NEW.{field} < '0001-01-01' OR date(NEW.{field}, '+0 days') IS NULL OR date(NEW.{field}, '+0 days') != NEW.{field})"
            checks.append(f"(NEW.{field} IS NULL OR {invalid})" if required else f"(NEW.{field} IS NOT NULL AND {invalid})")
        if table=='person_events': checks.append("(NEW.date_end IS NOT NULL AND NEW.date_end < NEW.date_start)")
        guard=' OR '.join(checks)
        for action in ('INSERT','UPDATE'):
            connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS exact_{table}_{action.lower()} BEFORE {action} ON {table} WHEN {guard} BEGIN SELECT RAISE(ABORT,'exact calendar dates and ordered periods required'); END")

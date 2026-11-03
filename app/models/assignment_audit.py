"""Append-only assignment operations, separate from effective-dated history."""
from datetime import datetime, UTC
from sqlalchemy import DateTime, ForeignKey, String, JSON, CheckConstraint, event
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class AssignmentAudit(Base):
    __tablename__ = 'assignment_audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    assignment_id: Mapped[int] = mapped_column(ForeignKey('person_assignments.id'), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    operation: Mapped[str] = mapped_column(String(30))
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(String(2000))
    __table_args__ = (CheckConstraint("operation IN ('create','edit','orders','complete','transfer','annul','restore')", name='assignment_audit_operation'),)


@event.listens_for(Base.metadata, 'after_create')
def sqlite_guards(metadata, connection, **kwargs):
    if connection.dialect.name != 'sqlite': return
    for action in ('UPDATE', 'DELETE'):
        connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS assignment_audit_no_{action.lower()} BEFORE {action} ON assignment_audit BEGIN SELECT RAISE(ABORT,'assignment audit is append only'); END")

    fields = ('person_id','staff_position_id','assigned_from','assigned_to','assignment_order_number',
              'assignment_order_date','release_order_number','release_order_date','completion_reason','completion_note')
    changed = ' OR '.join(f'NEW.{f} IS NOT OLD.{f}' for f in fields)
    connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS assignment_annulled_guard BEFORE UPDATE ON person_assignments WHEN OLD.annulled_at IS NOT NULL AND (NEW.annulled_at IS NOT NULL OR {changed}) BEGIN SELECT RAISE(ABORT,'restore annulled assignment before editing'); END")

"""Append-only event corrections, independent of medical and document audits."""
from datetime import datetime, UTC
from sqlalchemy import DateTime, ForeignKey, String, JSON, CheckConstraint, event, inspect
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base


class PersonEventCorrection(Base):
    __tablename__ = 'person_event_corrections'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey('person_events.event_id'), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    operation: Mapped[str] = mapped_column(String(30))
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (CheckConstraint("operation IN ('type_change','annul')", name='event_correction_operation'),)


@event.listens_for(Base.metadata, 'after_create')
def sqlite_guards(target, connection, **kwargs):
    if connection.dialect.name != 'sqlite' or 'person_event_corrections' not in inspect(connection).get_table_names(): return
    for action in ('UPDATE', 'DELETE'):
        connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS event_correction_no_{action.lower()} BEFORE {action} ON person_event_corrections BEGIN SELECT RAISE(ABORT,'event corrections are append only'); END")
    connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS person_event_no_delete BEFORE DELETE ON person_events BEGIN SELECT RAISE(ABORT,'annul event instead of deleting'); END")
    connection.exec_driver_sql("CREATE TRIGGER IF NOT EXISTS person_event_annulled_immutable BEFORE UPDATE ON person_events WHEN OLD.annulled_at IS NOT NULL BEGIN SELECT RAISE(ABORT,'annulled event is immutable'); END")

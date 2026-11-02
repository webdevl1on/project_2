from datetime import date, datetime
from typing import Optional
from sqlalchemy import (
    Integer,
    String,
    Date,
    ForeignKey,
    Text, Boolean, CheckConstraint, text, DateTime
)
from sqlalchemy.orm import Mapped, mapped_column, validates
from app.database.base import Base


class PersonEvent(Base):
    __tablename__ = "person_events"

    event_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    person_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("persons.person_id"),
        nullable=False,
        index=True
    )

    event_type_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("event_types.event_type_id"),
        nullable=False,
        index=True
    )

    event_subtype_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("event_subtypes.event_subtype_id"),
        nullable=True,
        index=True
    )

    date_start: Mapped[date] = mapped_column(
        Date, nullable=False,  index=True
    )

    duration: Mapped[Optional[int]]= mapped_column(Integer)
    
    date_end: Mapped[Optional[date]] = mapped_column(Date)

    annulled_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    annulment_reason: Mapped[Optional[str]] = mapped_column(Text)
    annulled_by: Mapped[Optional[int]] = mapped_column(ForeignKey('users.id'))

    planned_end: Mapped[Optional[date]] = mapped_column(Date)

    completion_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"), nullable=False)

    __table_args__ = (
        CheckConstraint("(annulled_at IS NULL AND annulment_reason IS NULL AND annulled_by IS NULL) OR (annulled_at IS NOT NULL AND length(trim(annulment_reason)) > 0 AND annulment_reason IS NOT NULL)", name="event_annulment_reason"),
        CheckConstraint("planned_end IS NULL OR planned_end >= date_start", name="event_planned_period"),
        CheckConstraint("NOT completion_confirmed OR date_end IS NOT NULL", name="event_confirmed_end"),
    )

    order_date: Mapped[Optional[date]] = mapped_column(Date)

    order_number: Mapped[Optional[str]]= mapped_column(String)

    purpose: Mapped[Optional[str]]= mapped_column(String)

    location: Mapped[Optional[str]]= mapped_column(Text)

    note: Mapped[Optional[str]]= mapped_column(Text)

    event_status: Mapped[Optional[str]]= mapped_column(String)

    @validates("date_start", "date_end", "order_date", "planned_end")
    def validate_exact_dates(self, key, value):
        from app.utils.date_utils import parse_exact_date
        return parse_exact_date(value, required=key == "date_start")

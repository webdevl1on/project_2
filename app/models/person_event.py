from datetime import date
from typing import Optional
from sqlalchemy import (
    Integer,
    String,
    Date,
    ForeignKey,
    Text
)
from sqlalchemy.orm import Mapped, mapped_column
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

    order_date: Mapped[Optional[date]] = mapped_column(Date)

    order_number: Mapped[Optional[str]]= mapped_column(String)

    purpose: Mapped[Optional[str]]= mapped_column(String)

    location: Mapped[Optional[str]]= mapped_column(Text)

    note: Mapped[Optional[str]]= mapped_column(Text)

    event_status: Mapped[Optional[str]]= mapped_column(String)
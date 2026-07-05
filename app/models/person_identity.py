from datetime import date, datetime, UTC
from typing import Optional
from typing import TYPE_CHECKING
from sqlalchemy import (
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.person_history_model import HistoryModel


if TYPE_CHECKING:
    from app.models.person import Person


class PersonName(HistoryModel):
    __tablename__ = "person_names"

    person_name_id: Mapped[int] = mapped_column(
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

    surname: Mapped[str] = mapped_column(
        String
    )
    name: Mapped[str] = mapped_column(
        String
    )
    patronymic: Mapped[Optional[str]] = mapped_column(
        String
    )
    surname_latin: Mapped[Optional[str]] = mapped_column(
        String
    )
    name_latin: Mapped[Optional[str]] = mapped_column(
        String
    )
    patronymic_latin: Mapped[Optional[str]] = mapped_column(
        String
    )
    person: Mapped["Person"] = relationship(
        back_populates="names"
    )


class Passport(HistoryModel):
    __tablename__ = "passports"

    passport_id: Mapped[int] = mapped_column(
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
    passport_type: Mapped[Optional[str]]= mapped_column(String)
    passport_series: Mapped[Optional[str]]= mapped_column(String)
    passport_number: Mapped[Optional[str]]= mapped_column(String)
    passport_issued_by: Mapped[Optional[str]] = mapped_column(String)
    passport_issued_date: Mapped[Optional[date]] = mapped_column(Date)
    passport_expire_date: Mapped[Optional[date]] = mapped_column(Date)
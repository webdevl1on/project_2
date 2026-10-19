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
from app.models.partial_date_mixin import PartialDateMixin, date_projection
from app.date_fields import DATE_FIELDS

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


class Passport(PartialDateMixin, HistoryModel):
    __tablename__ = "passports"
    __date_fields__ = {
        "passport_issued": DATE_FIELDS["passport.passport_issued_date"],
        "passport_expire": DATE_FIELDS["passport.passport_expire_date"],
    }

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
    passport_issued_day: Mapped[int | None] = mapped_column(Integer)
    passport_issued_month: Mapped[int | None] = mapped_column(Integer)
    passport_issued_year: Mapped[int | None] = mapped_column(Integer)
    passport_expire_day: Mapped[int | None] = mapped_column(Integer)
    passport_expire_month: Mapped[int | None] = mapped_column(Integer)
    passport_expire_year: Mapped[int | None] = mapped_column(Integer)
    _passport_issued_date: Mapped[date | None] = mapped_column("passport_issued_date", Date)
    _passport_expire_date: Mapped[date | None] = mapped_column("passport_expire_date", Date)
    passport_issued_date = date_projection("passport_issued")
    passport_expire_date = date_projection("passport_expire")

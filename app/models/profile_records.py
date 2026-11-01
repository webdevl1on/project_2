"""Independent profile records; no inferred facts, current-state copies or tasks."""
from datetime import date
from sqlalchemy import Date, String, ForeignKey, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, validates, relationship
from app.database.base import Base
from app.models.staff import SystemTimestamps, exact_date
from app.models.geography import GeographicFields


class PersonEducation(SystemTimestamps, Base):
    __tablename__ = 'person_education'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'), index=True)
    person: Mapped['Person'] = relationship()
    level_code: Mapped[str] = mapped_column(String(40))
    started_on: Mapped[date | None] = mapped_column(Date)
    ended_on: Mapped[date | None] = mapped_column(Date)
    institution: Mapped[str | None] = mapped_column(String(500))
    faculty: Mapped[str | None] = mapped_column(String(500))
    specialty: Mapped[str | None] = mapped_column(String(500))
    __table_args__ = (
        CheckConstraint("length(trim(level_code)) > 0"),
        CheckConstraint('ended_on IS NULL OR started_on IS NULL OR ended_on >= started_on'),
    )

    @validates('started_on','ended_on')
    def validate_date(self, key, value):
        return exact_date(value, False)


class PersonFamilyMember(GeographicFields, SystemTimestamps, Base):
    __tablename__ = 'person_family_members'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'), index=True)
    person: Mapped['Person'] = relationship()
    kinship: Mapped[str] = mapped_column(String(30))
    full_name: Mapped[str] = mapped_column(String(500))
    birth_on: Mapped[date | None] = mapped_column(Date)
    death_on: Mapped[date | None] = mapped_column(Date)
    phone: Mapped[str | None] = mapped_column(String(100))
    address_text: Mapped[str | None] = mapped_column(String(2000))
    street_id: Mapped[int | None] = mapped_column(ForeignKey('geo_units.id', ondelete='SET NULL'))
    street: Mapped[str | None] = mapped_column(String(250))
    street_type: Mapped[str | None] = mapped_column(String(250))
    house: Mapped[str | None] = mapped_column(String(250))
    corps: Mapped[str | None] = mapped_column(String(250))
    building: Mapped[str | None] = mapped_column(String(250))
    apartment: Mapped[str | None] = mapped_column(String(250))
    room: Mapped[str | None] = mapped_column(String(250))
    __table_args__ = (
        CheckConstraint('length(trim(full_name)) > 0'),
        CheckConstraint("length(trim(kinship)) > 0"),
        CheckConstraint("validation_status IN ('matched','mismatch','unknown')"),
        CheckConstraint('death_on IS NULL OR birth_on IS NULL OR death_on >= birth_on'),
    )

    @validates('birth_on','death_on')
    def validate_date(self, key, value):
        return exact_date(value, False)


class PersonDirective(SystemTimestamps, Base):
    __tablename__ = 'person_directives'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'), index=True)
    person: Mapped['Person'] = relationship()
    number: Mapped[str | None] = mapped_column(String(300))
    issued_on: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (
        CheckConstraint('number IS NULL OR length(number) <= 300'),
        CheckConstraint('issued_on IS NOT NULL OR (number IS NOT NULL AND length(trim(number)) > 0)'),
    )

    @validates('issued_on')
    def validate_date(self, key, value):
        return exact_date(value, False)


MODELS = {'education': PersonEducation, 'family': PersonFamilyMember, 'directives': PersonDirective}
NEW_TABLE_NAMES = {model.__tablename__ for model in MODELS.values()}

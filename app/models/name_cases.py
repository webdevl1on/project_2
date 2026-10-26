"""Verified global vocabulary and snapshots attached to a specific name history."""
from sqlalchemy import String, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base
from app.models.staff import SystemTimestamps


class CaseColumns:
    nominative: Mapped[str | None] = mapped_column(String(100))
    genitive: Mapped[str | None] = mapped_column(String(100))
    dative: Mapped[str | None] = mapped_column(String(100))
    accusative: Mapped[str | None] = mapped_column(String(100))
    instrumental: Mapped[str | None] = mapped_column(String(100))
    locative: Mapped[str | None] = mapped_column(String(100))
    vocative: Mapped[str | None] = mapped_column(String(100))


class NameDictionary(CaseColumns, SystemTimestamps, Base):
    __tablename__ = "name_dictionaries"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    sex: Mapped[str] = mapped_column(String(6))
    base_form: Mapped[str] = mapped_column(String(100))
    normalized_key: Mapped[str] = mapped_column(String(100), index=True)
    is_verified: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (
        UniqueConstraint("kind", "sex", "normalized_key"),
        CheckConstraint("kind IN ('surname','name','patronymic')"),
        CheckConstraint("sex IN ('male','female')"),
    )


class PersonNameCases(CaseColumns, SystemTimestamps, Base):
    __tablename__ = "person_name_cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_name_id: Mapped[int] = mapped_column(ForeignKey("person_names.person_name_id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    base_form: Mapped[str] = mapped_column(String(100))
    sex: Mapped[str | None] = mapped_column(String(6))
    is_verified: Mapped[bool] = mapped_column(default=False)
    __table_args__ = (UniqueConstraint("person_name_id", "kind"),
                      CheckConstraint("kind IN ('surname','name','patronymic')"),
                      CheckConstraint("sex IS NULL OR sex IN ('male','female')"))


class NameDictionaryImport(SystemTimestamps, Base):
    __tablename__ = "name_dictionary_imports"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(20))

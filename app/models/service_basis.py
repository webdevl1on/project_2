"""Document-owned service bases and an independent advisory TCC directory."""
from datetime import date
from sqlalchemy import String, Date, ForeignKey, CheckConstraint, UniqueConstraint, Index, text, event
from sqlalchemy.orm import Mapped, mapped_column, validates
from app.database.base import Base
from app.models.staff import SystemTimestamps, exact_date

NEW_TABLE_NAMES = {'tcc_offices', 'person_service_bases', 'tcc_imports'}
DATE_FIELDS = ('mobilization_date', 'contract_signed_date', 'contract_start_date', 'enlistment_order_date')


class TccOffice(SystemTimestamps, Base):
    __tablename__ = 'tcc_offices'
    id: Mapped[int] = mapped_column(primary_key=True)
    official_name: Mapped[str] = mapped_column(String(500))
    normalized_name: Mapped[str] = mapped_column(String(500))
    type: Mapped[str] = mapped_column(String(30))
    region: Mapped[str | None] = mapped_column(String(250))
    settlement: Mapped[str | None] = mapped_column(String(250))
    normalized_region: Mapped[str] = mapped_column(String(250), default='')
    normalized_settlement: Mapped[str] = mapped_column(String(250), default='')
    parent_tcc_id: Mapped[int | None] = mapped_column(ForeignKey('tcc_offices.id'))
    is_active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (
        UniqueConstraint('normalized_name', 'normalized_region', 'normalized_settlement', name='unique_tcc_identity'),
        CheckConstraint("type IN ('regional','city','district','united_district','department')"),
        CheckConstraint('parent_tcc_id IS NULL OR parent_tcc_id != id'),
        CheckConstraint('is_active IN (0,1)'),
        CheckConstraint('length(trim(official_name)) BETWEEN 1 AND 500'),
        CheckConstraint('region IS NULL OR length(region) <= 250'),
        CheckConstraint('settlement IS NULL OR length(settlement) <= 250'),
    )


class PersonServiceBasis(SystemTimestamps, Base):
    __tablename__ = 'person_service_bases'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'), index=True)
    service_type: Mapped[str] = mapped_column(String(20))
    is_current: Mapped[bool] = mapped_column(default=False)
    mobilization_date: Mapped[date | None] = mapped_column(Date)
    region: Mapped[str | None] = mapped_column(String(250))
    settlement: Mapped[str | None] = mapped_column(String(250))
    document_tcc_name: Mapped[str | None] = mapped_column(String(500))
    tcc_office_id: Mapped[int | None] = mapped_column(ForeignKey('tcc_offices.id'))
    match_status: Mapped[str] = mapped_column(String(10), default='unknown')
    document_verified: Mapped[bool] = mapped_column(default=False)
    contract_signed_date: Mapped[date | None] = mapped_column(Date)
    contract_start_date: Mapped[date | None] = mapped_column(Date)
    enlistment_order_date: Mapped[date | None] = mapped_column(Date)
    enlistment_order_number: Mapped[str | None] = mapped_column(String(100))
    contract_unit: Mapped[str | None] = mapped_column(String(250))
    __table_args__ = (
        CheckConstraint("service_type IN ('mobilization','contract')"),
        CheckConstraint("match_status IN ('matched','mismatch','unknown')"),
        CheckConstraint('is_current IN (0,1) AND document_verified IN (0,1)'),
        CheckConstraint('document_tcc_name IS NULL OR length(document_tcc_name) <= 500'),
        CheckConstraint('region IS NULL OR length(region) <= 250'),
        CheckConstraint('settlement IS NULL OR length(settlement) <= 250'),
        CheckConstraint('enlistment_order_number IS NULL OR length(enlistment_order_number) <= 100'),
        CheckConstraint('contract_unit IS NULL OR length(contract_unit) <= 250'),
        CheckConstraint("service_type != 'contract' OR (mobilization_date IS NULL AND region IS NULL AND settlement IS NULL AND document_tcc_name IS NULL AND tcc_office_id IS NULL)"),
        CheckConstraint("service_type != 'mobilization' OR (contract_signed_date IS NULL AND contract_start_date IS NULL AND enlistment_order_date IS NULL AND enlistment_order_number IS NULL AND contract_unit IS NULL)"),
        Index('one_current_service_basis', 'person_id', unique=True, sqlite_where=text('is_current = 1')),
    )

    @validates(*DATE_FIELDS)
    def validate_date(self, key, value):
        return exact_date(value, False)


class TccImport(SystemTimestamps, Base):
    __tablename__ = 'tcc_imports'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(10))


def install_date_guards(connection):
    invalid = ' OR '.join(
        f"(NEW.{field} IS NOT NULL AND (length(NEW.{field}) != 10 OR NEW.{field} < '0001-01-01' OR date(NEW.{field}, '+0 days') IS NULL OR date(NEW.{field}, '+0 days') != NEW.{field}))"
        for field in DATE_FIELDS)
    for action in ('insert', 'update'):
        connection.exec_driver_sql(f"CREATE TRIGGER IF NOT EXISTS exact_service_basis_{action} BEFORE {action.upper()} ON person_service_bases WHEN {invalid} BEGIN SELECT RAISE(ABORT,'exact service basis dates required'); END")


@event.listens_for(PersonServiceBasis.__table__, 'after_create')
def _dates(target, connection, **kwargs):
    if connection.dialect.name == 'sqlite':
        install_date_guards(connection)

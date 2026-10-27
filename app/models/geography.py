"""Text snapshots coexist with optional, non-authoritative dictionary links."""
from sqlalchemy import String, ForeignKey, Index, CheckConstraint, Date, text
from sqlalchemy.orm import Mapped, mapped_column
from datetime import date
from app.database.base import Base
from app.models.staff import SystemTimestamps

class GeoUnit(SystemTimestamps, Base):
    __tablename__ = "geo_units"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(250))
    normalized_name: Mapped[str] = mapped_column(String(250), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("geo_units.id"), index=True)
    iso_code: Mapped[str | None] = mapped_column(String(3), index=True)
    katottg_code: Mapped[str | None] = mapped_column(String(25), index=True)
    __table_args__ = (CheckConstraint("kind IN ('country','region','district','community','settlement','street')"),)

class GeoAlias(Base):
    __tablename__ = "geo_aliases"
    id: Mapped[int] = mapped_column(primary_key=True)
    unit_id: Mapped[int] = mapped_column(ForeignKey("geo_units.id"), index=True)
    name: Mapped[str] = mapped_column(String(250))
    normalized_name: Mapped[str] = mapped_column(String(250), index=True)
    historical: Mapped[bool] = mapped_column(default=False)

class GeographicFields:
    country: Mapped[str | None] = mapped_column(String(250))
    country_id: Mapped[int | None] = mapped_column(ForeignKey("geo_units.id", ondelete="SET NULL"))
    region: Mapped[str | None] = mapped_column(String(250))
    region_id: Mapped[int | None] = mapped_column(ForeignKey("geo_units.id", ondelete="SET NULL"))
    district: Mapped[str | None] = mapped_column(String(250))
    district_id: Mapped[int | None] = mapped_column(ForeignKey("geo_units.id", ondelete="SET NULL"))
    community: Mapped[str | None] = mapped_column(String(250))
    community_id: Mapped[int | None] = mapped_column(ForeignKey("geo_units.id", ondelete="SET NULL"))
    settlement: Mapped[str | None] = mapped_column(String(250))
    settlement_id: Mapped[int | None] = mapped_column(ForeignKey("geo_units.id", ondelete="SET NULL"))
    settlement_type: Mapped[str | None] = mapped_column(String(60))
    validation_status: Mapped[str] = mapped_column(String(10), default="unknown")

class PersonBirthplace(GeographicFields, SystemTimestamps, Base):
    __tablename__ = "person_birthplaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.person_id"), unique=True)

class PersonAddress(GeographicFields, SystemTimestamps, Base):
    __tablename__ = "person_addresses"
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("persons.person_id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True)
    date_start: Mapped[date | None] = mapped_column(Date)
    date_end: Mapped[date | None] = mapped_column(Date)
    street_id: Mapped[int | None] = mapped_column(ForeignKey("geo_units.id", ondelete="SET NULL"))
    street: Mapped[str | None] = mapped_column(String(250))
    street_type: Mapped[str | None] = mapped_column(String(250))
    house: Mapped[str | None] = mapped_column(String(250))
    corps: Mapped[str | None] = mapped_column(String(250))
    building: Mapped[str | None] = mapped_column(String(250))
    apartment: Mapped[str | None] = mapped_column(String(250))
    room: Mapped[str | None] = mapped_column(String(250))
    postal_code: Mapped[str | None] = mapped_column(String(250))
    note: Mapped[str | None] = mapped_column(String(1000))
    __table_args__ = (
        CheckConstraint("kind IN ('registration','actual','correspondence')"),
        CheckConstraint("date_end IS NULL OR date_start IS NULL OR date_end >= date_start"),
        Index("one_active_address", "person_id", "kind", unique=True, sqlite_where=text("is_active = 1")),
    )

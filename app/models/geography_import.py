"""Source provenance and stable external keys; addresses still reference GeoUnit."""
from sqlalchemy import ForeignKey, String, UniqueConstraint, JSON
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base

class GeoSource(Base):
    __tablename__ = 'geo_sources'
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    metadata_json: Mapped[dict] = mapped_column(JSON)

class GeoImportLink(Base):
    __tablename__ = 'geo_import_links'
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(36))
    unit_id: Mapped[int] = mapped_column(ForeignKey('geo_units.id'), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('geo_sources.id'))
    source_version: Mapped[str] = mapped_column(String(30))
    package_digest: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON)
    __table_args__ = (UniqueConstraint('kind','external_id'),)

class GeoCityDistrict(Base):
    """A city subdivision, deliberately separate from administrative districts."""
    __tablename__ = 'geo_city_districts'
    id: Mapped[int] = mapped_column(primary_key=True)
    external_id: Mapped[str] = mapped_column(String(36), unique=True)
    name: Mapped[str] = mapped_column(String(250))
    katottg_code: Mapped[str] = mapped_column(String(25), unique=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey('geo_units.id'), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey('geo_sources.id'))
    source_version: Mapped[str] = mapped_column(String(30))
    package_digest: Mapped[str] = mapped_column(String(64))

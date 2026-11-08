from typing import Optional

from datetime import date,datetime
from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint,Index,CheckConstraint,text,Date,DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database.base import Base
from app.models.staff import SystemTimestamps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.staff import PersonAssignment


class Rank(Base):
    __tablename__ = "ranks"

    rank_id: Mapped[int] = mapped_column(
        Integer,
        primary_key = True,
        autoincrement = True,
    )
    code: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=False,
    )

    nominative: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    genitive: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    dative: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    accusative: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    instrumental: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    locative: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    vocative: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )    

class Position(SystemTimestamps, Base):
    __tablename__ = "positions"
    __table_args__ = (
        Index('active_staff_position_number','staff_version_id','position_number',unique=True,sqlite_where=text('annulled_at IS NULL'),postgresql_where=text('annulled_at IS NULL')),
        CheckConstraint('valid_to IS NULL OR valid_from IS NULL OR valid_to>=valid_from',name='org_position_period'),
        CheckConstraint("annulled_at IS NULL OR (annulment_reason IS NOT NULL AND length(trim(annulment_reason)) BETWEEN 1 AND 2000)",name='org_position_annul_reason'),
    )
    org_unit_id: Mapped[int | None] = mapped_column(ForeignKey('org_units.id'),index=True)
    managed_unit_id: Mapped[int | None] = mapped_column(ForeignKey('org_units.id'))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    annulled_at: Mapped[datetime | None] = mapped_column(DateTime)
    annulment_reason: Mapped[str | None] = mapped_column(String(2000))
    annulled_by: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    @validates('valid_from','valid_to')
    def validate_org_date(self,key,value):
        from app.models.staff import exact_date
        return exact_date(value,False)

    staff_version_id: Mapped[int] = mapped_column(ForeignKey("staff_versions.id"), index=True)
    staff_version: Mapped["StaffVersion"] = relationship(back_populates="positions")

    position_id: Mapped[int] = mapped_column(
        Integer,
        primary_key = True,
        autoincrement = True,
    )

    position_number: Mapped[int] = mapped_column(
        Integer,
    )
    
    code: Mapped[str] = mapped_column(
            String,
            nullable=False,
        )

    unit_short: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    name_short: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    name_nominative: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )   
    name_genitive: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )   
    name_dative: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )   
    name_accusative: Mapped[str] = mapped_column(
        String,
        nullable=False,
    ) 
    name_instrumental: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    name_locative: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    name_vocative: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    persons: Mapped[list["PersonAssignment"]] = relationship(
    back_populates="position"
    )
from typing import Optional

from sqlalchemy import Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

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
    __table_args__ = (UniqueConstraint("staff_version_id", "position_number"),)
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
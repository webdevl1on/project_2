from datetime import date
from typing import TYPE_CHECKING
from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.person_identity import PersonName

class Person(Base):
    __tablename__ = "persons"

    person_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
        )
    tax_number: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=True
    )
    birth_date: Mapped[date] = mapped_column(
        Date,
        nullable=True
    )
    names: Mapped[list[PersonName]] = relationship(
        back_populates="person"
    )

    
    
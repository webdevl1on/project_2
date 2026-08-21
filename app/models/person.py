from datetime import date
from typing import TYPE_CHECKING
from sqlalchemy import Date, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.person_identity import PersonName
    from app.models.person_military_service import PersonRank
    from app.models.person_military_service import PersonServiceHistory

class Person(Base):
    __tablename__ = "persons"

    def __repr__(self):
        return f"<Person id={self.person_id}, tax={self.tax_number}"
    
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
    names: Mapped[list["PersonName"]] = relationship(
        back_populates="person"
    )
    ranks: Mapped[list["PersonRank"]] = relationship(
        back_populates="person"
    )
    service_history: Mapped[list["PersonServiceHistory"]] = relationship(
    back_populates="person"
    )
    
    
from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from app.models.person import Person
    from app.models.reference_book import Position

class PersonPosition(Base):
    __tablename__ = "person_positions"

    person_position_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.person_id"),
        nullable=False,
        index=True,
        unique=True,
    )

    position_id: Mapped[int] = mapped_column(
        ForeignKey("positions.position_id"),
        nullable=False,
        index=True,
        unique=True,
    )
    
    person: Mapped["Person"] = relationship(
        back_populates = "positions"
    )
    position: Mapped["Position"] = relationship(
        back_populates = "persons" 
    )

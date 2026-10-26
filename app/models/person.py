from typing import TYPE_CHECKING
from sqlalchemy import Integer, String, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.database.base import Base

if TYPE_CHECKING:
    from app.models.person_identity import PersonName
    from app.models.person_military_service import PersonRank
    from app.models.person_military_service import PersonServiceHistory
    from app.models.staff import PersonAssignment

class Person(Base):
    __tablename__ = "persons"

    def __repr__(self):
        return f"<Person id={self.person_id}, tax={self.tax_number}"
    person_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
        )
    sex: Mapped[str | None] = mapped_column(
        String(6), CheckConstraint("sex IS NULL OR sex IN ('male','female')"), nullable=True
    )

    @validates("sex")
    def validate_sex(self, key, value):
        from app.validators.name_cases import sex
        return sex(value, required=False)

    tax_number: Mapped[str] = mapped_column(
        String,
        unique=True,
        nullable=True
    )
    birth_day: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    birth_month: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    birth_year: Mapped[int | None] = mapped_column(
        Integer,
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
    positions: Mapped[list["PersonAssignment"]] = relationship(
    back_populates="person"
    )

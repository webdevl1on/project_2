from datetime import date, datetime, UTC
from typing import Optional
from typing import TYPE_CHECKING
from sqlalchemy import (
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.reference_book import Rank
from app.models.person_history_model import HistoryModel
if TYPE_CHECKING:
    from app.models.person import Person

#----- History of ranks-----

class PersonRank(HistoryModel):
    __tablename__ = "person_ranks"

    def __repr__(self):
        return f"<PersonRank id={self.person_id}, rank_id={self.person_rank_id}, rank={self.rank}, order_number={self.rank_order_number}, order_date={self.rank_order_date}"
                

    person_rank_id: Mapped[int] = mapped_column(
        Integer,
        primary_key = True,
        autoincrement = True
    )

    person_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("persons.person_id"),
        nullable=False,
        index=True
    )
    rank_id: Mapped[int] = mapped_column(
    ForeignKey("ranks.rank_id"),
    nullable=False,
    )
    rank_order_number: Mapped[Optional[str]] = mapped_column(String)
    rank_order_date: Mapped[Optional[date]] = mapped_column(Date)
    rank: Mapped["Rank"] = relationship()
    person: Mapped["Person"] = relationship(
        back_populates="ranks"
    )

#----- History of service-----

class PersonServiceHistory(HistoryModel):
    __tablename__ = "person_service_history"

    person_service_history_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    person_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("persons.person_id"),
        nullable=False,
        index=True,
    )

    service_type: Mapped[str] = mapped_column(
        String,
        nullable=True,
    )

    military_unit: Mapped[Optional[str]] = mapped_column(
        String,
    )

    position: Mapped[Optional[str]] = mapped_column(
        String,
    )

    position_date: Mapped[Optional[date]] = mapped_column(
        Date,
    )

    order_number: Mapped[Optional[str]] = mapped_column(
        String,
    )

    order_date: Mapped[Optional[date]] = mapped_column(
        Date,
    )

    person: Mapped["Person"] = relationship(
    back_populates="service_history"
    )
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
from app.models.partial_date_mixin import PartialDateMixin, date_projection
from app.date_fields import DATE_FIELDS
if TYPE_CHECKING:
    from app.models.person import Person

#----- History of ranks-----

class PersonRank(PartialDateMixin, HistoryModel):
    __tablename__ = "person_ranks"
    __date_fields__ = {"rank_order": DATE_FIELDS["rank.rank_order_date"]}

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
    rank_order_day: Mapped[int | None] = mapped_column(Integer)
    rank_order_month: Mapped[int | None] = mapped_column(Integer)
    rank_order_year: Mapped[int | None] = mapped_column(Integer)
    _rank_order_date: Mapped[date | None] = mapped_column("rank_order_date", Date)
    rank_order_date = date_projection("rank_order")
    rank: Mapped["Rank"] = relationship()
    person: Mapped["Person"] = relationship(
        back_populates="ranks"
    )

#----- History of service-----

class PersonServiceHistory(PartialDateMixin, HistoryModel):
    __tablename__ = "person_service_history"
    __date_fields__ = {
        "position": DATE_FIELDS["service.position_date"],
        "order": DATE_FIELDS["service.order_date"],
    }

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

    position_day: Mapped[int | None] = mapped_column(Integer)
    position_month: Mapped[int | None] = mapped_column(Integer)
    position_year: Mapped[int | None] = mapped_column(Integer)
    _position_date: Mapped[date | None] = mapped_column("position_date", Date)
    position_date = date_projection("position")

    order_number: Mapped[Optional[str]] = mapped_column(
        String,
    )

    order_day: Mapped[int | None] = mapped_column(Integer)
    order_month: Mapped[int | None] = mapped_column(Integer)
    order_year: Mapped[int | None] = mapped_column(Integer)
    _order_date: Mapped[date | None] = mapped_column("order_date", Date)
    order_date = date_projection("order")

    person: Mapped["Person"] = relationship(
    back_populates="service_history"
    )

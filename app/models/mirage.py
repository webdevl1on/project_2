"""Unofficial candidate attachment; never contributes to staff occupancy."""
from sqlalchemy import ForeignKey,String,Index,CheckConstraint,text
from sqlalchemy.orm import Mapped,mapped_column
from app.database.base import Base
from app.models.staff import SystemTimestamps

class PersonPositionMirage(SystemTimestamps,Base):
    __tablename__='person_position_mirages'
    id: Mapped[int]=mapped_column(primary_key=True)
    person_id: Mapped[int]=mapped_column(ForeignKey('persons.person_id'),index=True)
    staff_position_id: Mapped[int]=mapped_column(ForeignKey('positions.position_id'),index=True)
    status: Mapped[str]=mapped_column(String(20),default='waiting')
    note: Mapped[str|None]=mapped_column(String(1000))
    cancel_reason: Mapped[str|None]=mapped_column(String(1000))
    converted_assignment_id: Mapped[int|None]=mapped_column(ForeignKey('person_assignments.id'))
    __table_args__=(CheckConstraint("status IN ('waiting','converted','cancelled')"),
        CheckConstraint("status != 'converted' OR converted_assignment_id IS NOT NULL"),
        Index('one_waiting_mirage_per_person','person_id',unique=True,sqlite_where=text("status='waiting'")))

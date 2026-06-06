from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    Text,
    ForeignKey
)

from app.database.db import Base


class PersonEvent(Base):
    __tablename__ = "person_events"

    event_id = Column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    person_id = Column(
        Integer,
        ForeignKey("persons.person_id"),
        nullable=False,
        index=True
    )

    event_type_id = Column(
        Integer,
        ForeignKey("event_types.event_type_id"),
        nullable=False,
        index=True
    )

    event_subtype_id = Column(
        Integer,
        ForeignKey("event_subtypes.event_subtype_id"),
        nullable=True,
        index=True
    )

    date_start = Column(
        Date,
        nullable=False,
        index=True
    )

    duration = Column(Integer)
    
    date_end = Column(Date)

    order_date = Column(Date)

    order_number = Column(String)

    purpose = Column(String)

    location = Column(String)

    note = Column(Text)

    event_status = Column(String)
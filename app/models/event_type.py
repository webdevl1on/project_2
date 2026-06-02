from sqlalchemy import Column, Integer, String, Boolean
from app.database.db import Base

class EventType(Base):
    __tablename__ = "event_types"

    event_type_id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String, nullable=False)
    event_name = Column(String, nullable=False)
    event_color = Column(String)
    event_is_active = Column(Boolean, default=True)
    event_exclusive = Column(Boolean, default=True)
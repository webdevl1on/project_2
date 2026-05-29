from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.database.db import Base

class EventSubtype(Base):
    __tablename__ = "event_subtypes"

    event_subtype_id = Column(Integer, primary_key=True, autoincrement=True)
    event_type_id = Column(Integer, ForeignKey("event_types.event_type_id"), nullable=False)
    event_subtype = Column(String, nullable=False)
    event_subtype_name = Column(String, nullable=False)
    
    event_subtype_is_active = Column(Boolean, default=True)
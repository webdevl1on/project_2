from sqlalchemy import Column, ColumnCollection, Integer, String
from app.database.db import Base

class Person(Base):
    __tablename__ = "persons"

    person_id = Column(Integer, primary_key=True, autoincrement=True)
    pib = Column(String, nullable=False)
    rank = Column(String)
    position = Column(String)
    phone = Column(String)
    status = Column(String)

    
from sqlalchemy import Column, Integer, String, Date
from app.database.db import Base

class Person(Base):
    __tablename__ = "persons"

    person_id = Column(Integer, primary_key=True, autoincrement=True)
    pib = Column(String, nullable=False)
    rank = Column(String)
    birth_date = Column(Date)
    position = Column(String)
    phone = Column(String)
    status = Column(String)

    
from sqlalchemy import Column, ColumnCollection, Integer, String
from app.database.db import Base

class Person(Base):
    __tablename__ = "persons"

    id = Column(Integer, primary_key=True)
    pib = Column(String)
    rank = Column(String)
    position = Column(String)
    phone = Column(String)
    status = Column(String)

    
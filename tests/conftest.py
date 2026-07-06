import pytest
from app.database.base import Base
from app.database.db_test import SessionLocal_test, engine_test
from app import models

@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine_test)
    Base.metadata.create_all(bind=engine_test)

    db = SessionLocal_test()
    try:
        yield db
    finally:
        db.close()
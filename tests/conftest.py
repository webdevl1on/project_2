import pytest
from app.database.db import SessionLocal_test

@pytest.fixture
def db():
    db =SessionLocal_test()
    yield db
    db.close()
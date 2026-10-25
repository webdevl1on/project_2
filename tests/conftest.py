from tests.staff_fixtures import install_legacy_staff_fixture
install_legacy_staff_fixture()
import pytest
from app.database.base import Base
from app.database.db_test import SessionLocal_test, engine_test
from app import models

@pytest.fixture
def db():
    Base.metadata.drop_all(bind=engine_test)
    Base.metadata.create_all(bind=engine_test)

    db = SessionLocal_test(info={"legacy_staff_fixture":True})
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def legacy_staff_sessions(request):
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    if request.module.__name__.split(".")[-1] not in {"test_person_positions","test_table_field_catalog","test_date_system","test_partial_date_models"}:
        yield
        return
    def mark(session, transaction):
        session.info["legacy_staff_fixture"]=True
    event.listen(Session,"after_transaction_create",mark)
    try:yield
    finally:event.remove(Session,"after_transaction_create",mark)

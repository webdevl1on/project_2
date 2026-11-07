# Explicit legacy test connection, never production or a working SQLite.
import os
import tempfile
from pathlib import Path
os.environ.setdefault('PROJECT2_ENV','testing')
os.environ.setdefault('DATABASE_URL','sqlite:///'+str(Path(tempfile.mkdtemp(prefix='project2-legacy-'))/'app.sqlite3'))
if os.environ['PROJECT2_ENV']!='testing':raise RuntimeError('Tests require PROJECT2_ENV=testing.')
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


@pytest.fixture(autouse=True)
def existing_security_contract(monkeypatch):
    # Existing regressions exercise the retained, explicitly enabled protection.
    monkeypatch.setenv('PROJECT2_AUTH_ENABLED','1')

# Stable synthetic-only key configuration; never used by app runtime or real DBs.
os.environ.setdefault('PROJECT2_MFA_KEYS','{"test":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}')
os.environ.setdefault('PROJECT2_MFA_CURRENT_KEY','test')
os.environ.setdefault('PROJECT2_WEBAUTHN_RP_ID','testserver')
os.environ.setdefault('PROJECT2_WEBAUTHN_ORIGINS','["https://testserver"]')
from sqlalchemy import event
from app.models.mfa import MfaKeyState
@event.listens_for(MfaKeyState.__table__,'after_create')
def synthetic_mfa_key_state(table,connection,**kwargs):
    from app.security.mfa_config import encrypt,MARKER
    connection.execute(table.insert().values(id=1,ciphertext=encrypt(MARKER)))

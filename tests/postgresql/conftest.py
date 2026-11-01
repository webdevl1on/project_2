"""Only project2_ci; every test owns a random, disposable schema, never a database reset."""
import os
import uuid
from pathlib import Path
import pytest
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config

@pytest.fixture
def pg_factory(monkeypatch):
    raw=os.environ.get('PROJECT2_TEST_DATABASE_URL')
    if not raw:pytest.skip('PROJECT2_TEST_DATABASE_URL is required for actual PostgreSQL tests')
    url=make_url(raw)
    if url.drivername!='postgresql+psycopg' or url.database!='project2_ci':raise RuntimeError('Refusing PostgreSQL tests outside project2_ci.')
    schema='project2_test_'+uuid.uuid4().hex
    admin=create_engine(url)
    with admin.begin() as db:db.exec_driver_sql('CREATE SCHEMA '+schema)
    engine=create_engine(url,connect_args={'options':f'-c search_path={schema},public -c timezone=UTC -c lock_timeout=10000'})
    monkeypatch.setenv('PROJECT2_ENV','testing');monkeypatch.setenv('DATABASE_URL',raw)
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    try:
        with engine.begin() as db:
            db.exec_driver_sql('CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)')
            cfg.attributes['connection']=db
            command.upgrade(cfg,'head')
        yield sessionmaker(bind=engine,autoflush=False)
    finally:
        engine.dispose()
        with admin.begin() as db:db.exec_driver_sql('DROP SCHEMA '+schema+' CASCADE')
        admin.dispose()

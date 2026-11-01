from pathlib import Path
import os
import tempfile
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.base import Base

if os.environ.get('PROJECT2_ENV') != 'testing':
    raise RuntimeError('Legacy test database is available only in PROJECT2_ENV=testing.')
DATA_DIR = Path(tempfile.mkdtemp(prefix='project2-legacy-tests-'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEST_DB_PATH = DATA_DIR / "project2_test.db"

engine_test = create_engine(f"sqlite:///{TEST_DB_PATH}", echo =False)
SessionLocal_test = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)

def get_test_db():
    db = SessionLocal_test()
    try:
        yield db
    finally:
        db.close()

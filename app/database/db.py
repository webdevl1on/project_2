from pathlib import Path
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.base import Base

DATA_DIR = Path("data/database")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "project2.db"

# Explicit development target only. Missing configuration never redirects main DB.
if os.environ.get('PROJECT2_DEV_AUTH_BYPASS')=='1' and os.environ.get('PROJECT2_DEV_AUTH_DATABASE'):
    # Avoid importing services here: transactions imports this module.
    import re
    candidate=Path(os.environ['PROJECT2_DEV_AUTH_DATABASE']).resolve()
    if candidate==DB_PATH.resolve() or not re.search(r'(^|[_-])(test|testing|dev)([_\-.]|$)',candidate.name,re.I) or not candidate.is_file():
        raise ValueError('PROJECT2_DEV_AUTH_DATABASE має вказувати на наявну окрему test/dev SQLite, не project2.db.')
    DB_PATH=candidate

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

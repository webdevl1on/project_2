from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATA_DIR = Path("data/database")
DATA_DIR.mkdir(parents=True, exist_ok=True)
TEST_DB_PATH = DATA_DIR / "project2_test.db"

engine_test = create_engine(f"sqlite:///{TEST_DB_PATH}", echo =False)
SessionLocal_test = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)
Base = declarative_base()
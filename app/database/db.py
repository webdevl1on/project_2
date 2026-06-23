from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATA_DIR = Path("data/database")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "project2.db"
TEST_DB_PATH = DATA_DIR / "project2_test.db"
#DATABASE_URL = "sqlite:///data/database/project2.db"
#DATABASE_TEST_URL = "sqlite:///data/database/project2_test.db"

engine = create_engine(f"sqlite:///{DB_PATH}", echo=False)
engine_test = create_engine(f"sqlite:///{TEST_DB_PATH}", echo =False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
SessionLocal_test = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)
Base = declarative_base()
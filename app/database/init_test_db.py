from app.database.db_test import engine_test
from app.database.base import Base
import app.models  # Registers all models in Base.metadata.

def init_test_db():
    Base.metadata.create_all(bind=engine_test)

if __name__ == "__main__":
    init_test_db()
    print("TEST Database initialized successfully.")

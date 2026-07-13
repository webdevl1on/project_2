from app.database.db import engine
from app.database.base import Base
import app.models  # Registers all models in Base.metadata.

def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")

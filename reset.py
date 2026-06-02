from pathlib import Path
from app.database.init_db import init_db   
from app.services.seed_all import seed_all

DB_FILE = Path("data/database/project_2.db")

if DB_FILE.exists():
    DB_FILE.unlink()  # delete the existing database file
    print("Existing database file deleted.")


init_db()
print("Database initialized successfully.")
seed_all()
print("Database seeded successfully.")
print("Database reset completed.")
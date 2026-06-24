from pathlib import Path
from app.database.init_db import init_db  
from app.database.db import DATA_DIR
from app.seeds.seed_structure import seed_all_structure

DB_FILE = DATA_DIR / "project2.db"

if DB_FILE.exists():
    DB_FILE.unlink()  # delete the existing database file
    print("Existing database file deleted.")

init_db()
print("Database initialized successfully.")
seed_all_structure()
print("Database seeded successfully.")
print("Database reset completed.")
from pathlib import Path
from app.database.db import SessionLocal
from app.seeds.seed_event_types import EVENT_TYPES
from app.seeds.seed_event_subtypes import EVENT_SUBTYPES
from app.database.init_db import init_db  
from app.database.db import DATA_DIR
from app.seeds.seed_structure import seed_all_structure

DB_FILE = DATA_DIR / "project2.db"

if DB_FILE.exists():
    DB_FILE.unlink()  # delete the existing database file
    print("Existing database file deleted.")

init_db()
print("Database initialized successfully.")
db = SessionLocal()
seed_all_structure(db)
db.commit()
db.close()
print("Database seeded successfully.")
print("Database reset completed.")
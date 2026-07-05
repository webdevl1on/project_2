from pathlib import Path
from app.database.db_test import SessionLocal_test
from app.seeds.seed_event_types import EVENT_TYPES
from app.seeds.seed_event_subtypes import EVENT_SUBTYPES
from app.database.init_test_db import init_test_db  
from app.database.db_test import DATA_DIR
from app.seeds.seed_structure import seed_all_structure

DB_FILE = DATA_DIR / "project2_test.db"

if DB_FILE.exists():
    DB_FILE.unlink()
    print("Existing TEST database file deleted")

init_test_db()
print("TEST Database initialized successfully")
db = SessionLocal_test()
seed_all_structure(db)
db.commit()
db.close()
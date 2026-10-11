from app.database.db import SessionLocal
from app.config import EXCEL_PATH
from app.seeds.seed_reference import seed_positions

db = SessionLocal()

try:
    seed_positions(db, EXCEL_PATH)
    db.commit()
    print("Посади успішно оновлено!")
except Exception:
    db.rollback()
    raise
finally:
    db.close()
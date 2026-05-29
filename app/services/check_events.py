from app.database.db import SessionLocal
from app.models.event_type import EventType

db = SessionLocal()

rows = db.query(EventType).all()

print("COUNT =", len(rows))

for row in rows:
    print(
        row.event_type_id,
        row.event_type,
        row.event_name
    )

db.close()
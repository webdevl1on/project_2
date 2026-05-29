from datetime import date
from app.database.db import SessionLocal
from app import models



db = SessionLocal()

event = models.PersonEvent(
    person_id=1,
    event_type_id=5,
    event_subtype_id=2,
    date_start=date(2026, 8, 8),
    duration=10,  
    order_number = "123",
    purpose = "навчання fvp",
    location = "Житомир",
    note = "Примітка до події"
)

db.add(event)
db.commit()
print("Person event added successfully.")
db.close()
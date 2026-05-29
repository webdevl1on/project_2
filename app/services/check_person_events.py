from app.database.db import SessionLocal
from app.models.person_event import PersonEvent

db = SessionLocal()

for event in db.query(PersonEvent).all():
    print(f"Event ID: {event.event_id}, Person ID: {event.person_id}, Event Type ID: {event.event_type_id}, "
          f"Event Subtype ID: {event.event_subtype_id}, Date Start: {event.date_start}, Duration: {event.duration}, "
          f"Date End: {event.date_end}, Order Date: {event.order_date}, Order Number: {event.order_number}, "
          f"Purpose: {event.purpose}, Location: {event.location}, ------------")
db.close()
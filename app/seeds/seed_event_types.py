
from app.models.event_type import EventType

EVENT_TYPES = [
    ("SERVICE", "Служба"),
    ("DUTY", "Чергування"),
    ("DAY_OFF", "Вихідний"),
    ("VACATION", "Відпустка"),
    ("BUSINESS_TRIP", "Відрядження"),
    ("HOSPITAL", "Лікарняний"),
    ("UNAUTHORIZED_ABSENCE", "СЗЧ")
]
 
def seed_event_types(db):
    for event_type, event_name in EVENT_TYPES:

        exists = (
            db.query(EventType)
            .filter(EventType.event_type == event_type)
            .first()
        )
        if exists:
            print("Already exists")
            continue
        db.add(EventType(event_type=event_type, event_name=event_name))
        db.flush()
    print("=== SEED EVENT_TYPES END ===") 
    

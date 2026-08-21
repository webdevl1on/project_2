from app.models.event_type import EventType
from app.models.event_subtype import EventSubtype

EVENT_SUBTYPES = {
    "BUSINESS_TRIP": [
        ("BUSINESS_TRIP_TRAINING", "БЗВП"),
        ("BUSINESS_TRIP_STUDING", "Навчання"),
        ("BUSINESS_TRIP_MISSION", "СБЗ"),
        ("BUSINESS_TRIP_OTHER", "Інше"),
    ],
    "VACATION": [
        ("VACATION_ANNUAL", "Основна"),
        ("VACATION_FAMILY", "За сімейними обставинами"),
        ("VACATION_REHABILITATION", "Реабілітаційна"),
        ("VACATION_OTHER", "Інше"),
    ],
    "DUTY": [
        ("DUTY_DAY", "Добове чергування"),
        ("DUTY_CHECKPOINT", "КПП"),
        ("DUTY_PATROL", "Патруль"),
        ("DUTY_OTHER", "Інше"),
    ],
    "HOSPITAL": [
        ("HOSPITAL_OUTPATIENT", "Амбулаторне лікування"),
        ("HOSPITAL_INPATIENT", "Стаціонар"),
        ("HOSPITAL_OTHER", "Інше"),
    ],
}
def seed_event_subtypes(db):

    for event_type_code, subtypes in EVENT_SUBTYPES.items():
        event_type = (
            db.query(EventType)
            .filter(EventType.event_type == event_type_code)
            .first()
        )
        if not event_type:
            continue
        for subtype_code, subtype_name in subtypes:
            exists = (
                db.query(EventSubtype)
                .filter(EventSubtype.event_type_id == event_type.event_type_id,
                    EventSubtype.event_subtype == subtype_code).first()
                )
            if exists:
                continue
            db.add(EventSubtype(event_type_id=event_type.event_type_id, event_subtype=subtype_code, event_subtype_name=subtype_name))
            db.flush()
    print("=== SEED EVENT_SUBTYPES END ===") 


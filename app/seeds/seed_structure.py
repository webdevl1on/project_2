from app.seeds.seed_event_types import seed_event_types
from app.seeds.seed_event_subtypes import seed_event_subtypes

def seed_all_structure(db):
    seed_event_types(db)
    db.flush()
    seed_event_subtypes(db)



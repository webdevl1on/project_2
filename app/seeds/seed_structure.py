from app.seeds.seed_event_types import seed_event_types
from app.seeds.seed_event_subtypes import seed_event_subtypes
from app.seeds.seed_reference import seed_ranks
from app.config import EXCEL_PATH
from app.seeds.seed_reference import seed_positions

def seed_all_structure(db):

    seed_event_types(db)
    db.flush()

    seed_event_subtypes(db)

    seed_ranks(db)

    seed_positions(db, EXCEL_PATH)

    print("=== COMMIT ===")
    db.commit()
    print("=== COMMIT DONE ===")

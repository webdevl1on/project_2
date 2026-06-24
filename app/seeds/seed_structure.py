from app.seeds.seed_event_types import seed_event_types
from app.seeds.seed_event_subtypes import seed_event_subtypes
def seed_all_structure():
    seed_event_types()
    seed_event_subtypes()
if __name__ == "__main__":
    seed_all_structure()
    print("All data seeded successfully.")


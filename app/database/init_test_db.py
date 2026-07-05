from app.database.db_test import engine_test
from app.database.base import Base
from app.models.person import Person
from app.models.person_event import PersonEvent
from app.models.event_type import EventType
from app.models.event_subtype import EventSubtype

def init_test_db():
    Base.metadata.create_all(bind=engine_test)

if __name__ == "__main__":
    init_test_db()
    print("TEST Database initialized successfully.")
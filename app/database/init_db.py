from app.database.db import Base, engine
from app.models.person import Person
from app.models.person_event import PersonEvent
from app.models.event_type import EventType
from app.models.event_subtype import EventSubtype

def init_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
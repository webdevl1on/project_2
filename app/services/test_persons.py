from app.database.db import SessionLocal
from app.models.person import Person
from app.models.event_type import EventType
from app.models.event_subtype import EventSubtype

db = SessionLocal()

persons = [
    Person(
        pib="Іванов Іван Іванович",
        rank="Солдат",
        position="Оператор",
        status="В строю"
    ),
    Person(
        pib="Петренко Петро Петрович",
        rank="Старший солдат",
        position="Водій",
        status="В строю"
    )
]

db.add_all(persons)
db.commit()
print("Persons added to the database successfully.")

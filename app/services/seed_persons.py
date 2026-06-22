from datetime import date

from app.database.db import SessionLocal
from app.models.person import Person


def seed_persons():
    db = SessionLocal()

    try:
        persons = [
            Person(
                pib="Іваненко Іван Іванович",
                rank="Сержант",
                birth_date=date(1990, 5, 10),
                position="Командир відділення",
                phone="0501111111",
                status="active"
            ),
            Person(
                pib="Петренко Петро Петрович",
                rank="Солдат",
                birth_date=date(1995, 8, 20),
                position="Стрілець",
                phone="0502222222",
                status="active"
            ),
            Person(
                pib="Сидоренко Сергій Сергійович",
                rank="Старший солдат",
                birth_date=date(1992, 3, 15),
                position="Водій",
                phone="0503333333",
                status="vacation"
            ),
        ]

        db.add_all(persons)
        db.commit()

        print(f"Додано {len(persons)} осіб")

    finally:
        db.close()


if __name__ == "__main__":
    seed_persons()
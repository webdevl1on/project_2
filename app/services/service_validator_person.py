from app.database.db import SessionLocal
from app.models.person import Person

from app.validators.person_validator import PersonValidator


class PersonService:

    @staticmethod
    def create_person(
        pib,
        rank=None,
        birth_date=None,
        position=None,
        phone=None,
        status=None
    ):

        db = SessionLocal()

        try:

            person = Person(

                pib=PersonValidator.validate_person_pib(
                    pib
                ),

                rank=PersonValidator.validate_person_rank(
                    rank
                ),

                birth_date=PersonValidator.validate_person_birth_date(
                    birth_date
                ),

                phone=PersonValidator.validate_person_phone(
                    phone
                ),

                position=position,
                status=status
            )

            db.add(person)
            db.commit()
            db.refresh(person)

            return person

        finally:
            db.close()
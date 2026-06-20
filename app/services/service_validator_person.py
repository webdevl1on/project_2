from app.database.db import SessionLocal
from app.models.person import Person
from app.services.person_event_service import PersonEventService
from app.validators.person_validator import PersonValidator


class PersonService:

    @staticmethod
    def prepare_new_person(
        pib,
        rank=None,
        birth_date=None,
        position=None,
        phone=None,
        status=None
    ):
        new_person = Person(

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
        return new_person
    
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
            person = PersonService.prepare_new_person(
                pib,
                rank,
                birth_date,
                position,
                phone,
                status
            )

            db.add(person)
            db.commit()
            db.refresh(person)

            return person

        finally:
            db.close()

    @staticmethod
    def change_person(
        person_id,
        pib,
        rank=None,
        birth_date=None,
        position=None,
        phone=None,
        status=None
    ):
        db = SessionLocal()
        try:
            person_to_change = PersonEventService.get_person_or_raise(person_id, db)
            prepared_changes = PersonService.prepare_new_person(
                pib,
                rank,
                birth_date,
                position,
                phone,
                status
            )
            person_to_change.pib = prepared_changes.pib
            person_to_change.rank = prepared_changes.rank
            person_to_change.birth_date = prepared_changes.birth_date
            person_to_change.position = prepared_changes.position
            person_to_change.phone = prepared_changes.phone
            person_to_change.status = prepared_changes.status
            db.commit()
            db.refresh(person_to_change)
            return person_to_change
        finally:
            db.close()

from app.database.db import SessionLocal
from app.database.db_test import SessionLocal_test
from app.models.person import Person
from app.services.service_common_person_func import CommonPersonFunc



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
            person = CommonPersonFunc.prepare_new_person(
                pib,
                rank,
                birth_date,
                position,
                phone,
                status
            )
            return person


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
            person_to_change = CommonPersonFunc.get_person_or_raise(person_id, db)
            prepared_changes = CommonPersonFunc.prepare_new_person(
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

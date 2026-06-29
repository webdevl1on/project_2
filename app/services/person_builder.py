from app import models
from app.models.person import Person
from app.validators.person_validator import PersonValidator



class PersonBuilder:
    #Check person_id, if no person raise ERROR
    @staticmethod
    def get_person_or_raise(person_id, db):
        person = db.query(models.Person).filter(
            models.Person.person_id == person_id
        ).first()
        if not person:
            raise ValueError(f"Person with id {person_id} does not exist.")
        return person
    
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
from sqlalchemy import Null
from app import models
from app.models.person import Person
from app.models.person_identity import Passport, PersonName
from app.validators.person_validator import PersonValidator



class CommonPersonFunc:
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
    def ensure_tax_number_is_unique(person_tax_number, db):
        tax_number = db.query(models.Person).filter(
            models.Person.tax_number == person_tax_number).first()
        if tax_number is not Null and tax_number is not None:
            raise ValueError(f"Person with tax number {tax_number} already exist.")
        return tax_number
        
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
    def create_person(data, db):
        person_data = CommonPersonFunc.validate_person_base_data(data)
        name_data = CommonPersonFunc.validate_name_data(data)
                
        if not person_data["tax_number"] and not name_data["surname"]:
            raise ValueError("Surname or tax number required!")
        if person_data["tax_number"]:
            CommonPersonFunc.ensure_tax_number_is_unique(person_data["tax_number"], db)
        person = Person(**person_data)
        db.add(person)
        db.flush()
        name = CommonPersonFunc.add_name(
            person_id = person.person_id, **name_data)
        db.add(name)
        
    @staticmethod
    def add_name(
        person_id, 
        surname,
        name,
        patronymic,
        surname_latin,
        name_latin,
        patronymic_latin
        ):
        return PersonName(
            person_id=person_id,
            surname=surname,
            name=name,
            patronymic=patronymic,
            surname_latin=surname_latin,
            name_latin=name_latin,
            patronymic_latin=patronymic_latin
        )
    
    @staticmethod
    def add_pasport(
        person_id,
        passport_series,
        passport_number,
        passport_issued_by,
        passport_issued_date,
        passport_expire_date
    ):
        return Passport(
            person_id=person_id,
            passport_series = passport_series,
            passport_number = passport_number,
            passport_issued_by = passport_issued_by,
            passport_issued_date = passport_issued_date,
            passport_expire_date = passport_expire_date
        )
    
    @staticmethod
    def validate_person_base_data(data):
        return {
            "tax_number" : PersonValidator.validate_tax_number(data.get("tax_number")),
            "birth_date" : PersonValidator.validate_person_birth_date(data.get("birth_date"))
        }
    @staticmethod
    def validate_name_data(data):
        return {
            "surname": PersonValidator.validate_names(data.get("surname")),
            "name": PersonValidator.validate_names(data.get("name")),
            "patronymic": PersonValidator.validate_names(data.get("patronymic")),
            "surname_latin": PersonValidator.validate_names(data.get("surname_latin")),
            "name_latin": PersonValidator.validate_names(data.get("name_latin")),
            "patronymic_latin": PersonValidator.validate_names(data.get("patronymic_latin")),
        }
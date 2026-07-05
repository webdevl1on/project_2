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
    def get_person_tax_number_or_raise(person_tax_number, db):
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
        tax_number = PersonValidator.validate_tax_number(data['tax_number'])
        tax_number = CommonPersonFunc.get_person_tax_number_or_raise(tax_number, db)
        birth_date = PersonValidator.validate_person_birth_date(data["birth_date"])

        validated_name_data = {
            "surname" : PersonValidator.validate_names(data['surname']),
            "name" : PersonValidator.validate_names(data["name"]),
            "patronymic" : PersonValidator.validate_names(data['patronymic']),
            "surname_latin" : PersonValidator.validate_names(data["surname_latin"]),
            "name_latin" : PersonValidator.validate_names(data['name_latin']),
            "patronymic_latin" : PersonValidator.validate_names(data["patronymic_latin"])
        }
        validated_passport_data = {
            "passport_type" : passport_series,
            "passport_series" : passport_series,
            "passport_number" : passport_number,
            "passport_issued_by" :  passport_issued_by,
            "passport_issued_date" : passport_issued_date,
            "passport_expire_date" : passport_expire_date
        }
        
        if not validated_name_data['surname']  or not tax_number:
            raise ValueError("Name or tax number required!")
                
        person = Person(
            tax_number = tax_number,
            birth_date = birth_date
        )
        db.add(person)
        db.flush()
        name = CommonPersonFunc.add_name(person_id = person.person_id, **validated_name_data)
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
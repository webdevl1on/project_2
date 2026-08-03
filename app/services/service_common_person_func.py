from app import models
from app.models.person import Person
from app.models.person_identity import Passport, PersonName
from app.models.person_military_service import PersonRank
from app.validators.person_validator import PersonValidator
from datetime import date


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
    def ensure_tax_number_is_unique(person_tax_number, db, exclude_person_id=None):
        tax_number = db.query(models.Person).filter(
            models.Person.tax_number == person_tax_number).first()
        if tax_number is not None and tax_number.person_id != exclude_person_id:
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

                birth_date=PersonValidator.validate_date(
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
        rank_data = CommonPersonFunc.validate_rank_data(data)
                
        if not name_data["surname"] or not name_data["name"]:
            raise ValueError("Surname and name required!")
        if person_data["tax_number"]:
            CommonPersonFunc.ensure_tax_number_is_unique(person_data["tax_number"], db)
        person = Person(**person_data)
        db.add(person)
        db.flush()
        name = CommonPersonFunc.add_name(
            person.person_id,
            name_data,
            db,
        )
        db.add(name)
        if rank_data["rank"]:
            rank = CommonPersonFunc.add_rank(
                person_id=person.person_id, **rank_data
            )
            db.add(rank)
        db.commit()
        db.refresh(person)

        return person

    @staticmethod
    def update_person(person_id, data, db):
        person = CommonPersonFunc.get_person_or_raise(person_id, db)
        person_data = CommonPersonFunc.validate_person_base_data(data)
        name_data = CommonPersonFunc.validate_name_data(data)
        rank_data = CommonPersonFunc.validate_rank_data(data)

        if not name_data["surname"] or not name_data["name"]:
            raise ValueError("Surname and name required!")
        if person_data["tax_number"]:
            CommonPersonFunc.ensure_tax_number_is_unique(
                person_data["tax_number"],
                db,
                exclude_person_id=person_id,
            )

        person.tax_number = person_data["tax_number"]
        person.birth_date = person_data["birth_date"]

        current_name = (
            db.query(PersonName)
            .filter(
                PersonName.person_id == person_id,
                PersonName.date_to.is_(None),
            )
            .first()
        )
        if current_name is None:
            current_name = CommonPersonFunc.add_name(
                person_id=person_id,
                **name_data,
            )
            db.add(current_name)
        else:
            for field, value in name_data.items():
                setattr(current_name, field, value)

        current_rank = (
            db.query(PersonRank)
            .filter(
                PersonRank.person_id == person_id,
                PersonRank.date_to.is_(None),
            )
            .first()
        )
        has_rank_data = any(value is not None for value in rank_data.values())
        if current_rank is None and has_rank_data:
            current_rank = CommonPersonFunc.add_rank(
                person_id=person_id,
                **rank_data,
            )
            db.add(current_rank)
        elif current_rank is not None:
            for field, value in rank_data.items():
                setattr(current_rank, field, value)

        db.commit()
        db.refresh(person)
        return person


    @staticmethod
    def add_name(person_id, data, db):
        CommonPersonFunc.get_person_or_raise(person_id, db)
        name_data = CommonPersonFunc.validate_name_data(data)
        if not name_data["surname"] or not name_data["name"]:
            raise ValueError("Surname and name required!")
        
        return PersonName(
            person_id=person_id,
            surname=name_data.get("surname"),
            name=name_data.get("name"),
            patronymic=name_data.get("patronymic"),
            surname_latin=name_data.get("surname_latin"),
            name_latin=name_data.get("name_latin"),
            patronymic_latin=name_data.get("patronymic_latin"),  
        )
    @staticmethod
    def add_new_name(person_id, data, db):
        person = CommonPersonFunc.get_person_or_raise(person_id, db)
        name_data = CommonPersonFunc.validate_name_data(data)
        if not name_data["surname"] or not name_data["name"]:
            raise ValueError("Surname and name required!")
        person_name = PersonName(
            person_id=person_id,
            surname=name_data.get("surname"),
            name=name_data.get("name"),
            patronymic=name_data.get("patronymic"),
            surname_latin=name_data.get("surname_latin"),
            name_latin=name_data.get("name_latin"),
            patronymic_latin=name_data.get("patronymic_latin"),
            date_from = date.today(),
        )
        db.add(person_name)
        db.commit()
        db.refresh(person_name)
        return person_name
         
    
    @staticmethod
    def change_person_name(person_id, data, db):
        CommonPersonFunc.get_person_or_raise(person_id, db)
        # Find the current active name record
        current_name = (
            db.query(PersonName)
            .filter(PersonName.person_id == person_id,
                    PersonName.date_to.is_(None))
            .first()
        )
        if not current_name:
            raise ValueError("Current person name was not found")
        validated_data = {}
        for field in (
            "surname",
            "name",
            "patronymic",
            "surname_latin",
            "name_latin",
            "patronymic_latin",
        ):
            if field in data:
                validated_data[field] = PersonValidator.validate_names(data[field])
        # Keep old values for fields that were not passed
        new_surname = validated_data.get("surname", current_name.surname)
        new_name = validated_data.get("name", current_name.name)
        new_patronymic = validated_data.get("patronymic", current_name.patronymic)
        new_surname_latin = validated_data.get("surname_latin",current_name.surname_latin)
        new_name_latin = validated_data.get("name_latin",current_name.name_latin)
        new_patronymic_latin = validated_data.get("patronymic_latin",current_name.patronymic_latin)
        # Surname and name must exist after merging old and new values
        if not new_surname or not new_name:
            raise ValueError("Surname and name required!")
        # Close the old record and create a new historical record
        change_date = date.today()
        current_name.date_to = change_date

        new_person_name = PersonName(
            person_id=person_id,
            surname=new_surname,
            name=new_name,
            patronymic=new_patronymic,
            surname_latin=new_surname_latin,
            name_latin=new_name_latin,
            patronymic_latin=new_patronymic_latin,
            date_from=change_date,
            date_to=None,
        )

        db.add(new_person_name)
        db.commit()
        db.refresh(new_person_name)
        return new_person_name
    
    @staticmethod
    def update_person_name(person_id, person_name_id, data, db):
        # Find the exact name record that belongs to this person
        person_name = (
            db.query(PersonName)
            .filter(
                PersonName.person_id == person_id,
                PersonName.person_name_id == person_name_id,
            )
            .first()
        )

        if not person_name:
            raise ValueError("Person name record was not found.")

        # Validate only fields passed for update
        validated_data = {}

        for field in (
            "surname",
            "name",
            "patronymic",
            "surname_latin",
            "name_latin",
            "patronymic_latin",
        ):
            if field in data:
                validated_data[field] = PersonValidator.validate_names(data[field])

        # Check required values after applying updates
        final_surname = validated_data.get("surname", person_name.surname)
        final_name = validated_data.get("name", person_name.name)

        if not final_surname or not final_name:
            raise ValueError("Surname and name required!")

        # Update only fields that were passed
        for field, value in validated_data.items():
            setattr(person_name, field, value)

        db.commit()
        db.refresh(person_name)

        return person_name
    
    @staticmethod
    def add_rank(
        person_id,
        rank,
        rank_order_number,
        rank_order_date,
    ):
        return PersonRank(
            person_id=person_id,
            rank = rank,
            rank_order_number = rank_order_number,
            rank_order_date = rank_order_date,
            date_from = date.today(),
        )
    
    @staticmethod
    def change_person_rank(person_id, data, db):
        CommonPersonFunc.get_person_or_raise(person_id, db)
        current_rank = (
            db.query(PersonRank)
            .filter(PersonRank.person_id == person_id,
                    PersonRank.date_to.is_(None))
            .first()
        )
        if not current_rank:
            raise ValueError("Current person rank was not found")
        validated_data = {}
        if data.get("rank"):
            validated_data['rank'] = PersonValidator.validate_person_rank(data.get("rank"))
        if data.get("rank_order_number"):
            validated_data['rank'] = PersonValidator.validate_person_rank(data.get("rank_order_number"))
        if data.get("rank_order_date"):
            validated_data['rank_order_date'] = PersonValidator.validate_date(data.get("rank_order_date"))
        
        new_person_rank = PersonRank(
            person_id = person_id,
            rank = validated_data.get('rank'),
            rank_order_number = validated_data.get('rank_order_number'),
            rank_order_date = validated_data.get('rank_order_date'),
            
        )
        db.add(new_person_rank)
        db.commit()
        db.refresh(new_person_rank)
        return new_person_rank

    @staticmethod
    def update_person_rank(person_id, person_rank_id, data, db):
        person_rank = (
            db.query(PersonRank)
            .filter(
                PersonRank.person_id == person_id,
                PersonRank.person_rank_id == person_rank_id,
            )
            .first()
        )
        if not person_rank:
            raise ValueError("Person rank record was not found.")
        validated_data = {}
        if data.get("rank"):
            validated_data['rank'] = PersonValidator.validate_person_rank(data.get("rank"))
        if data.get("rank_order_number"):
            validated_data['rank'] = PersonValidator.validate_person_rank(data.get("rank_order_number"))
        if data.get("rank_order_date"):
            validated_data['rank_order_date'] = PersonValidator.validate_date(data.get("rank_order_date"))
        for key, value in validated_data.items():
            setattr(person_rank, key, value)
        db.commit()
        db.refresh(person_rank)

        return person_rank


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
    
#Validate different data   
    @staticmethod
    def validate_person_base_data(data):
        return {
            "tax_number" : PersonValidator.validate_tax_number(data.get("tax_number")),
            "birth_date" : PersonValidator.validate_date(data.get("birth_date"))
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
    
    @staticmethod
    def validate_rank_data(data):
        return {
            "rank" : PersonValidator.validate_person_rank(data.get("rank")),
            "rank_order_number" : PersonValidator.validate_person_rank(data.get("rank_order_number")),
            "rank_order_date" : PersonValidator.validate_date(data.get("rank_order_date")),
        }

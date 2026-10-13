from app import models
from app.models.person import Person
from app.models.person_identity import PersonName
from app.services.service_person_checking import ServicePersonCheck
from app.services.service_person_group_data_validation import DataGroupValidate

class ServicePersonCreate:

    @staticmethod
    def create_person(data, db):
        person_data = DataGroupValidate.validate_person_base_data(data)
        name_data = DataGroupValidate.validate_name_data(data)
                
        if not name_data["surname"] or not name_data["name"]:
            raise ValueError("Surname and name required!")
        if person_data["tax_number"]:
            ServicePersonCheck.ensure_tax_number_is_unique(person_data["tax_number"], db)
        person = Person(**person_data)
        db.add(person)
        db.flush()
        name = ServicePersonCreate.add_name(
            person.person_id,
            name_data,
            db,
        )
        db.add(name)
        db.commit()
        db.refresh(person)

        return person

    @staticmethod
    def update_person(person_id, data, db):
        person = db.get(Person, person_id)
        if not person:
            raise ValueError(f"Person with id {person_id} does not exist.")

        person_data = DataGroupValidate.validate_person_base_data(data)
        name_data = DataGroupValidate.validate_name_data(data)
        if not name_data["surname"] or not name_data["name"]:
            raise ValueError("Surname and name required!")

        if person_data["tax_number"]:
            ServicePersonCheck.ensure_tax_number_is_unique(
                person_data["tax_number"],
                db,
                exclude_person_id=person_id,
            )

        person.tax_number = person_data["tax_number"]
        person.birth_day = person_data["birth_day"]
        person.birth_month = person_data["birth_month"]
        person.birth_year = person_data["birth_year"]

        current_name = (
            db.query(PersonName)
            .filter(
                PersonName.person_id == person_id,
                PersonName.is_active.is_(True),
            )
            .first()
        )
        if not current_name:
            current_name = PersonName(person_id=person_id, **name_data)
            db.add(current_name)
        else:
            for field, value in name_data.items():
                setattr(current_name, field, value)

        db.commit()
        db.refresh(person)
        return person

    @staticmethod
    def add_name(person_id, data, db):
        ServicePersonCheck.get_person_or_raise(person_id, db)
        name_data = DataGroupValidate.validate_name_data(data)
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

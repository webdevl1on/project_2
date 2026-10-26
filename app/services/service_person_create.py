from app.repositories.person_repository import PersonRepository
from app.database.transactions import service_transaction
from app.models.person_identity import PersonName
from app.services.service_person_checking import ServicePersonCheck
from app.services.service_person_group_data_validation import DataGroupValidate

class ServicePersonCreate:

    @staticmethod
    def create_person(data, db, *, commit=True):
        with service_transaction(db, commit=commit):
            person_data = DataGroupValidate.validate_person_base_data(data)
            name_data = DataGroupValidate.validate_name_data(data)

            if not name_data["surname"] or not name_data["name"]:
                raise ValueError("Surname and name required!")
            if person_data["tax_number"]:
                ServicePersonCheck.ensure_tax_number_is_unique(person_data["tax_number"], db)
            person = PersonRepository.add_person(db, person_data)
            # add_name remains a validated, non-persisting factory used by seeding.
            PersonRepository.add_name(db, person.person_id, name_data)
        db.refresh(person)

        return person

    @staticmethod
    def update_person(person_id, data, db, *, commit=True):
        with service_transaction(db, commit=commit):
            person = PersonRepository.get_by_id(db, person_id)
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

            current_name = PersonRepository.current_name(db, person_id)
            if not current_name:
                current_name = PersonRepository.add_name(db, person_id, name_data)
            else:
                for field, value in name_data.items():
                    setattr(current_name, field, value)

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

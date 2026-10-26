from app.repositories.person_repository import PersonRepository
from app.database.transactions import service_transaction
from app.services.service_person_checking import ServicePersonCheck

from app.services.service_person_group_data_validation import DataGroupValidate



class ServicePersonNameFunc:
    @staticmethod
    def get_record(key, db):
        return PersonRepository.get_name(db, key)

    @staticmethod
    def add_new_name(person_id, data, db, *, commit=True):
        with service_transaction(db, commit=commit):
            ServicePersonCheck.get_person_or_raise(person_id, db)
            current_name = PersonRepository.current_name(db, person_id)
            if not current_name:
                raise ValueError("Current person name was not found")

            name_data = DataGroupValidate.validate_name_data(data)
            if not name_data["surname"] or not name_data["name"]:
                raise ValueError("Surname and name required!")
            person_name = PersonRepository.add_name(db, person_id, dict(
                surname=name_data.get("surname"),
                name=name_data.get("name"),
                patronymic=name_data.get("patronymic"),
                surname_latin=name_data.get("surname_latin"),
                name_latin=name_data.get("name_latin"),
                patronymic_latin=name_data.get("patronymic_latin"),
                is_active = True,
            ))
            current_name.is_active = False
        db.refresh(person_name)
        return person_name

    @staticmethod
    def update_person_name(person_name_id, data, db, *, commit=True):
        # Find the exact name record that belongs to this person
        with service_transaction(db, commit=commit):
            person_name = PersonRepository.get_name(db, person_name_id)
            if not person_name:
                raise ValueError("Person name record was not found.")

            # A partial update changes only supplied fields. A full browser form
            # still passes every field, including optional fields to be cleared.
            source_data = {
                "surname": data["surname"] if "surname" in data else person_name.surname,
                "name": data["name"] if "name" in data else person_name.name,
                "patronymic": data["patronymic"] if "patronymic" in data else person_name.patronymic,
                "surname_latin": data["surname_latin"] if "surname_latin" in data else person_name.surname_latin,
                "name_latin": data["name_latin"] if "name_latin" in data else person_name.name_latin,
                "patronymic_latin": data["patronymic_latin"] if "patronymic_latin" in data else person_name.patronymic_latin,
            }
            name_data = DataGroupValidate.validate_name_data(source_data)
            if not name_data["surname"] or not name_data["name"]:
                raise ValueError("Surname and name required!")

            person_name.surname = name_data["surname"]
            person_name.name = name_data["name"]
            person_name.patronymic = name_data["patronymic"]
            person_name.surname_latin = name_data["surname_latin"]
            person_name.name_latin = name_data["name_latin"]
            person_name.patronymic_latin = name_data["patronymic_latin"]

        db.refresh(person_name)

        return person_name

    @staticmethod
    def change_person_name_to_active(person_name_id, db, *, commit=True):
        with service_transaction(db, commit=commit):
            new_active_name = PersonRepository.get_name(db, person_name_id)
            if not new_active_name:
                raise ValueError("Person name not found")
            person_id = new_active_name.person_id
            previos_active_name = PersonRepository.current_name(db, person_id, exclude=person_name_id)
            if not previos_active_name:
                raise ValueError("Person active name not found")
            previos_active_name.is_active = False
            new_active_name.is_active = True

        return person_id

    @staticmethod
    def delete_person_name(person_name_id, confirmation, db, *, commit=True):
        with service_transaction(db, commit=commit):
            if confirmation != "DELETE":
                raise ValueError("Для видалення введіть DELETE")

            person_name = PersonRepository.get_name(db, person_name_id)
            if not person_name:
                raise ValueError("Person name not found")
            if person_name.is_active == True:
                raise ValueError("Cannot DELETE active record")
            person_id = person_name.person_id

            PersonRepository.delete(db, person_name)

        return person_id

from app import models
from app.models.person import Person
from app.models.person_identity import PersonName
from app.services.service_person_checking import ServicePersonCheck

from app.services.service_person_group_data_validation import DataGroupValidate



class ServicePersonNameFunc:
    @staticmethod
    def add_new_name(person_id, data, db):
        ServicePersonCheck.get_person_or_raise(person_id, db)
        current_name = (
                    db.query(PersonName)
                    .filter(PersonName.person_id == person_id,
                            PersonName.is_active.is_(True))
                    .first()
                )
        if not current_name:
            raise ValueError("Current person name was not found")
        
        name_data = DataGroupValidate.validate_name_data(data)
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
            is_active = True,
        )
        current_name.is_active = False
        db.add(person_name)
        db.commit()
        db.refresh(person_name)
        return person_name

    @staticmethod
    def update_person_name(person_name_id, data, db):
        # Find the exact name record that belongs to this person
        person_name = (
            db.query(PersonName)
            .filter(
                PersonName.person_name_id == person_name_id,
            )
            .first()
        )
        if not person_name:
            raise ValueError("Person name record was not found.")

        name_data = DataGroupValidate.validate_name_data(data)

        person_name.surname = name_data["surname"]
        person_name.name = name_data["name"]
        person_name.patronymic = name_data["patronymic"]
        person_name.surname_latin = name_data["surname_latin"]
        person_name.name_latin = name_data["name_latin"]
        person_name.patronymic_latin = name_data["patronymic_latin"]

        db.commit()
        db.refresh(person_name)

        return person_name

    @staticmethod
    def change_person_name_to_active(person_name_id, db):
        new_active_name = (db.query(PersonName)
                               .filter(PersonName.person_name_id == person_name_id,
                                       )
                                .first()
        )
        if not new_active_name:
                    raise ValueError("Person name not found")
        person_id = new_active_name.person_id
        previos_active_name = (db.query(PersonName)
                               .filter(PersonName.person_id == person_id,
                                       PersonName.is_active == True,
                                       PersonName.person_name_id != person_name_id,)
                               .first()
        )
        if not previos_active_name:
            raise ValueError("Person active name not found")
        previos_active_name.is_active = False
        new_active_name.is_active = True

        db.commit()
        return person_id

    @staticmethod
    def delete_person_name(person_name_id, confirmation, db):
        if confirmation != "DELETE":
            raise ValueError("Для видалення введіть DELETE")

        person_name = (db.query(PersonName)
                       .filter(PersonName.person_name_id == person_name_id)
                       .first()
        )
        if not person_name:
            raise ValueError("Person name not found")
        if person_name.is_active == True:
            raise ValueError("Cannot DELETE active record")    
        person_id = person_name.person_id

        db.delete(person_name)
        db.commit()

        return person_id


    
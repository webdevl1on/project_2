from app import models
from app.models.person import Person
from app.models.person_identity import Passport, PersonName
from app.models.person_military_service import PersonRank
from app.validators.person_validator import PersonValidator
from datetime import date
from app.services.service_person_group_data_validation import DataGroupValidate
from app.services.service_person_rank import ServicePersonRankFunc
from app.services.service_person_checking import ServicePersonCheck

class CommonPersonFunc:
    pass 


    @staticmethod
    def update_person(person_id, data, db):
        person = ServicePersonCheck.get_person_or_raise(person_id, db)
        person_data = DataGroupValidate.validate_person_base_data(data)
        name_data = DataGroupValidate.validate_name_data(data)
        rank_data = DataGroupValidate.validate_rank_data(data)

        if not name_data["surname"] or not name_data["name"]:
            raise ValueError("Surname and name required!")
        if person_data["tax_number"]:
            ServicePersonCheck.ensure_tax_number_is_unique(
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
            current_rank = ServicePersonRankFunc.add_rank(
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




    

   






#add and another passport functions
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
    


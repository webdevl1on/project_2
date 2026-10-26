"""One atomic creation of a person, name snapshots and the initial rank."""
from app.database.transactions import service_transaction
from app.repositories.person_repository import PersonRepository
from app.services.service_person_create import ServicePersonCreate
from app.services.service_person_rank import ServicePersonRankFunc
from app.services.name_cases import save_personal, NameFormError
from app.name_cases import NAME_PARTS
from app.validators.person_validator import PersonValidator
from app.services.service_person_group_data_validation import DataGroupValidate
from app.validators.name_cases import sex
from app.services.service_person_checking import ServicePersonCheck


def register_person(db, data):
    with service_transaction(db):
        try:
            sex(data.get("sex"))
        except ValueError as error:
            raise NameFormError(str(error), ["sex_male"]) from error
        for kind, label in NAME_PARTS.items():
            try:
                PersonValidator.validate_names(data.get(kind))
            except ValueError as error:
                raise NameFormError(f"{label}: {error}", [kind]) from error
        try:
            PersonValidator.validate_tax_number(data.get("tax_number"))
        except ValueError as error:
            raise NameFormError("РНОКПП має містити рівно 10 цифр.", ["tax_number"]) from error
        if data.get("tax_number"):
            try:
                ServicePersonCheck.ensure_tax_number_is_unique(data["tax_number"].strip(), db)
            except ValueError as error:
                raise NameFormError("Людина з таким РНОКПП уже існує.", ["tax_number"]) from error
        try:
            DataGroupValidate.validate_person_base_data(data)
        except ValueError as error:
            raise NameFormError(f"Дата народження: {error}", ["birth_day"]) from error
        try:
            rank_id = int(data.get("rank_id", ""))
        except (ValueError, TypeError) as error:
            raise NameFormError("Оберіть поточне військове звання.", ["rank_id"]) from error
        person = ServicePersonCreate.create_person(data, db, commit=False)
        current_name = PersonRepository.current_name(db, person.person_id)
        save_personal(db, current_name, person.sex, data)
        ServicePersonRankFunc.add_rank(person.person_id, {"rank_id": rank_id}, db, commit=False)
    db.refresh(person)
    return person

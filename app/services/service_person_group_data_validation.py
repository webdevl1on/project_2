from app.validators.person_validator import PersonValidator
from app.utils.date_utils import validate_field_date
from app.date_fields import BIRTH_DATE


class DataGroupValidate:


    @staticmethod
    def validate_person_base_data(data):
        birth_components = validate_field_date(
            BIRTH_DATE,
            data.get("birth_day"),
            data.get("birth_month"),
            data.get("birth_year"),
        )
        return {
            "tax_number" : PersonValidator.validate_tax_number(data.get("tax_number")),
            **birth_components.as_dict(),
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

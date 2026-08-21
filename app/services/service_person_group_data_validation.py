
from app.validators.person_validator import PersonValidator


class DataGroupValidate:


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
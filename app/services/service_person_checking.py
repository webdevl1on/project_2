from app.repositories.person_repository import PersonRepository


class ServicePersonCheck:

    @staticmethod
    def get_person_or_raise(person_id, db):
        person = PersonRepository.get_by_id(db, person_id)
        if not person:
            raise ValueError(f"Person with id {person_id} does not exist.")
        return person

    @staticmethod
    def ensure_tax_number_is_unique(person_tax_number, db, exclude_person_id=None):
        tax_number = PersonRepository.get_by_tax_number(db, person_tax_number)
        if tax_number is not None and tax_number.person_id != exclude_person_id:
            raise ValueError(f"Person with tax number {tax_number} already exist.")
        return tax_number

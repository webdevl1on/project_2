from app import models


class ServicePersonCheck:

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
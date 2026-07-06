from app.models.person import Person
from app.models.person_identity import PersonName


class PersonRepository:
    
    @staticmethod
    def get_by_id(db, person_id):
        return db.query(Person).filter(Person.person_id == person_id).first()
    
    @staticmethod
    def get_by_tax_number(db, tax_number):
        return db.query(Person).filter(Person.tax_number == tax_number).first()
    
    @staticmethod
    def add_person(db, person_data):
        person = Person(**person_data)
        db.add(person)
        db.flush()
        return person
    
    @staticmethod
    def add_name(db, person_id, name_data):
        name = PersonName(
            person_id = person_id,
            **name_data
        )
        db.add(name)
        return name
from sqlalchemy import select
from app.models import PersonContact

class ContactRepository:
    @staticmethod
    def list(db,person_id):
        return list(db.scalars(select(PersonContact).where(PersonContact.person_id==person_id).order_by(PersonContact.id)))

    @staticmethod
    def get(db,person_id,key):
        return db.scalar(select(PersonContact).where(PersonContact.id==key,PersonContact.person_id==person_id))

    @staticmethod
    def add(db,person_id,kind):
        record=PersonContact(person_id=person_id,contact_type=kind)
        db.add(record)
        return record

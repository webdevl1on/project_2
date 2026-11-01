"""Additional record queries only; transaction ownership belongs to the service."""
from sqlalchemy import select
from app.models import Person, PersonnelAudit
from app.models.profile_records import MODELS


class ProfileRecordRepository:
    @staticmethod
    def person(db, person_id):
        return db.get(Person, person_id)

    @staticmethod
    def get(db, kind, key):
        return db.get(MODELS[kind], key)

    @staticmethod
    def rows(db, kind, person_id):
        model = MODELS[kind]
        return list(db.scalars(select(model).where(model.person_id == person_id).order_by(model.id.desc())))

    @staticmethod
    def audits(db, kind, person_id):
        return list(db.scalars(select(PersonnelAudit).where(
            PersonnelAudit.person_id == person_id, PersonnelAudit.entity == kind
        ).order_by(PersonnelAudit.id.desc())))

    @staticmethod
    def add(db, row):
        db.add(row)
        return row

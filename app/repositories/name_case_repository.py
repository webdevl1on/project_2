"""Dictionary and personal-case persistence. No commits or grammatical guesses."""
from sqlalchemy import select, func
from app.models.name_cases import NameDictionary, PersonNameCases, NameDictionaryImport


class NameCaseRepository:
    @staticmethod
    def find(db, kind, sex, key):
        return db.scalar(select(NameDictionary).where(NameDictionary.kind == kind,
                         NameDictionary.sex == sex, NameDictionary.normalized_key == key))

    @staticmethod
    def get(db, key):
        return db.get(NameDictionary, key)

    @staticmethod
    def list(db, kind, query="", page=1):
        filters = [NameDictionary.kind == kind]
        if query:
            filters.append(NameDictionary.normalized_key.contains(query, autoescape=True))
        total = db.scalar(select(func.count()).select_from(NameDictionary).where(*filters))
        rows = db.scalars(select(NameDictionary).where(*filters)
                          .order_by(NameDictionary.normalized_key, NameDictionary.sex, NameDictionary.id)
                          .offset((page - 1) * 50).limit(50)).all()
        return rows, total

    @staticmethod
    def personal(db, name_id):
        return db.scalars(select(PersonNameCases).where(PersonNameCases.person_name_id == name_id)).all()

    @staticmethod
    def add(db, record):
        db.add(record)
        return record

    @staticmethod
    def imported(db, key):
        return db.get(NameDictionaryImport, key)

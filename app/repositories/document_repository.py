"""Document queries/writes, without commits or business decisions."""
from sqlalchemy import select
from app.models import DocumentType, PersonDocumentState, PersonDocument, DocumentDetails, DrivingCategory, DocumentFile, DocumentAudit, Passport, Person


class DocumentRepository:
    @staticmethod
    def types(db): return list(db.scalars(select(DocumentType).order_by(DocumentType.id)))

    @staticmethod
    def type(db, code): return db.scalar(select(DocumentType).where(DocumentType.code==code))

    @staticmethod
    def state(db, person_id, type_id):
        return db.scalar(select(PersonDocumentState).where(PersonDocumentState.person_id==person_id, PersonDocumentState.document_type_id==type_id))

    @staticmethod
    def document(db, key): return db.get(PersonDocument, key)

    @staticmethod
    def person(db, key): return db.get(Person, key)

    @staticmethod
    def passport(db, key): return db.get(Passport, key)

    @staticmethod
    def details(db, key): return db.get(DocumentDetails, key)

    @staticmethod
    def records(db, person_id): return list(db.scalars(select(PersonDocument).where(PersonDocument.person_id==person_id).order_by(PersonDocument.id.desc())))

    @staticmethod
    def categories(db, key): return list(db.scalars(select(DrivingCategory).where(DrivingCategory.document_id==key).order_by(DrivingCategory.id)))

    @staticmethod
    def files(db, key): return list(db.scalars(select(DocumentFile).where(DocumentFile.document_id==key).order_by(DocumentFile.id)))

    @staticmethod
    def file(db, key): return db.get(DocumentFile, key)

    @staticmethod
    def audits(db, person_id): return list(db.scalars(select(DocumentAudit).where(DocumentAudit.person_id==person_id).order_by(DocumentAudit.id.desc())))

    @staticmethod
    def archived_snapshot(db, key):
        row=db.scalar(select(DocumentAudit).where(DocumentAudit.document_id==key,DocumentAudit.operation=='archive').order_by(DocumentAudit.id.desc()))
        return row.changes.get('snapshot',{}) if row else {}

    @staticmethod
    def add(db, value): db.add(value); return value

    @staticmethod
    def delete(db, value): db.delete(value)

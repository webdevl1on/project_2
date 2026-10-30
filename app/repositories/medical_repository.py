"""Personnel queries; no commits and no personnel workflow decisions."""
from sqlalchemy import select, func, case, and_
from app.models import Person, MedicalExam, MedicalSelection, MedicalDocumentLink, PersonnelAudit, DocumentFile
from app.models.medical import MODELS


def active_exam_selection():
    """One chosen ID per person; shared by all readers, including SQL filters."""
    stats=select(MedicalExam.person_id,func.count().label('total'),func.count(MedicalExam.issued_on).label('dated'),func.max(MedicalExam.issued_on).label('latest')).where(MedicalExam.status=='COMPLETED').group_by(MedicalExam.person_id).subquery()
    newest=select(MedicalExam.person_id,func.count().label('ties'),func.min(MedicalExam.id).label('candidate')).join(stats,and_(MedicalExam.person_id==stats.c.person_id,MedicalExam.issued_on==stats.c.latest)).where(MedicalExam.status=='COMPLETED').group_by(MedicalExam.person_id).subquery()
    manual=select(MedicalSelection.person_id,MedicalExam.id.label('manual_id')).join(MedicalExam,and_(MedicalExam.id==MedicalSelection.exam_id,MedicalExam.person_id==MedicalSelection.person_id,MedicalExam.status=='COMPLETED')).subquery()
    return select(Person.person_id,case((manual.c.manual_id.is_not(None),manual.c.manual_id),(and_(stats.c.total==stats.c.dated,newest.c.ties==1),newest.c.candidate),else_=None).label('chosen_id'),case((manual.c.manual_id.is_not(None),False),(and_(stats.c.total>0, (stats.c.total!=stats.c.dated)|(func.coalesce(newest.c.ties,0)!=1)),True),else_=False).label('ambiguous')).outerjoin(stats,stats.c.person_id==Person.person_id).outerjoin(newest,newest.c.person_id==Person.person_id).outerjoin(manual,manual.c.person_id==Person.person_id).subquery('active_medical_exam')

class MedicalRepository:
    @staticmethod
    def person(db,pid):return db.get(Person,pid)
    @staticmethod
    def get(db,kind,key):return db.get(MODELS[kind],key)
    @staticmethod
    def rows(db,kind,pid):return list(db.scalars(select(MODELS[kind]).where(MODELS[kind].person_id==pid).order_by(MODELS[kind].id.desc())))
    @staticmethod
    def selection(db,pid):return db.get(MedicalSelection,pid)
    @staticmethod
    def active(db,pid):
        chosen=active_exam_selection()
        return db.execute(select(MedicalExam,chosen.c.ambiguous).select_from(chosen).outerjoin(MedicalExam,MedicalExam.id==chosen.c.chosen_id).where(chosen.c.person_id==pid)).first()
    @staticmethod
    def add(db,row):db.add(row);return row
    @staticmethod
    def links(db,pid):
        from app.models import PersonDocument
        return list(db.scalars(select(MedicalDocumentLink).join(PersonDocument,PersonDocument.id==MedicalDocumentLink.document_id).where(PersonDocument.person_id==pid).order_by(MedicalDocumentLink.id)))
    @staticmethod
    def files(db,document_id):return list(db.scalars(select(DocumentFile).where(DocumentFile.document_id==document_id,DocumentFile.is_removed.is_(False))))
    @staticmethod
    def audits(db,pid):return list(db.scalars(select(PersonnelAudit).where(PersonnelAudit.person_id==pid).order_by(PersonnelAudit.id.desc())))

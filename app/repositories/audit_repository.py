"""Read-only adapters over existing append-only journals, never a second audit DB."""
from sqlalchemy import select
from app import models as m

SYSTEM=((m.AccountAudit,'account'),(m.AccessAudit,'access'))
SUBJECT=((m.SubjectAudit,'subject'),(m.DocumentAudit,'document'),(m.PersonnelAudit,'personnel'),
         (m.AssignmentAudit,'assignment'),(m.PersonEventCorrection,'event'),(m.OrgAudit,'organization'))

def rows(db,kind):
    for model,source in SYSTEM if kind=='system' else SUBJECT:
        for row in db.scalars(select(model).order_by(model.id).execution_options(yield_per=500)):
            yield source,row

def lookups(db):
    return {
        'actors':dict(db.execute(select(m.User.id,m.User.username)).all()),
        'assignments':dict(db.execute(select(m.PersonAssignment.id,m.PersonAssignment.person_id)).all()),
        'events':dict(db.execute(select(m.PersonEvent.event_id,m.PersonEvent.person_id)).all()),
        'medical_documents':set(db.scalars(select(m.MedicalDocumentLink.document_id))),
    }

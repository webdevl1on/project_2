"""ACL persistence and batched subject resolution; caller owns the transaction."""
from datetime import date
from sqlalchemy import select,or_,and_,text
from app.models import User,Person,Position,PersonAssignment,StaffVersion
from app.models.organization import OrgUnit,OrgUnitState
from app.models.access import *
from app.database.locking import locked_get

class AccessRepository:
    @staticmethod
    def get(db,model,key):return locked_get(db,model,key)
    @staticmethod
    def add(db,row):db.add(row);return row
    @staticmethod
    def lock(db):
        if db.get_bind().dialect.name=='postgresql':db.execute(text("SELECT pg_advisory_xact_lock(hashtext(current_schema()),hashtext('project2_organization'))"))
    @staticmethod
    def all(db,model):return list(db.scalars(select(model)))
    @staticmethod
    def linked_users(db,person_ids):return list(db.scalars(select(User).where(User.person_id.in_(person_ids))))
    @staticmethod
    def topology(db,on):
        units=list(db.scalars(select(OrgUnit).where(OrgUnit.annulled_at.is_(None),OrgUnit.formed_on<=on,or_(OrgUnit.dissolved_on.is_(None),OrgUnit.dissolved_on>=on))))
        states=list(db.scalars(select(OrgUnitState).where(OrgUnitState.valid_from<=on,or_(OrgUnitState.valid_to.is_(None),OrgUnitState.valid_to>=on))))
        return units,states
    @staticmethod
    def subjects(db,on):
        from app.repositories.organization_staff_repository import effective_position
        positions=list(db.scalars(select(Position)))
        current=list(db.scalars(select(PersonAssignment).join(Position).join(StaffVersion).where(
            PersonAssignment.annulled_at.is_(None),PersonAssignment.assigned_from<=on,
            or_(PersonAssignment.assigned_to.is_(None),PersonAssignment.assigned_to>=on),
            StaffVersion.annulled_at.is_(None),StaffVersion.valid_from<=on,or_(StaffVersion.valid_to.is_(None),StaffVersion.valid_to>=on),effective_position(on))))
        previous=list(db.scalars(select(PersonAssignment).where(PersonAssignment.annulled_at.is_(None),PersonAssignment.assigned_to<on)))
        return positions,current,previous
    @staticmethod
    def rules(db,user_id,templates,policies,temporary):
        return list(db.scalars(select(AccessRule).where(AccessRule.revoked_at.is_(None),or_(
            AccessRule.user_id==user_id,AccessRule.template_id.in_(templates),AccessRule.policy_id.in_(policies),AccessRule.temporary_id.in_(temporary)))))
    @staticmethod
    def audit(db,limit=200):return list(db.scalars(select(AccessAudit).order_by(AccessAudit.id.desc()).limit(limit)))
    @staticmethod
    def review(db,user_id,reason):
        dialect=db.get_bind().dialect.name
        if dialect=='postgresql':from sqlalchemy.dialects.postgresql import insert
        else:from sqlalchemy.dialects.sqlite import insert
        from datetime import datetime,UTC
        stamp=datetime.now(UTC).replace(tzinfo=None)
        stmt=insert(AccessReview).values(user_id=user_id,status='OPEN',reason=reason,revision=1,created_at=stamp,updated_at=stamp).on_conflict_do_nothing(index_elements=['user_id'],index_where=text("status='OPEN'")).returning(AccessReview.id)
        return db.scalar(stmt)
    @staticmethod
    def affected_people(db,position_ids):
        return list(db.scalars(select(PersonAssignment.person_id).where(PersonAssignment.staff_position_id.in_(position_ids),PersonAssignment.annulled_at.is_(None))))
    @staticmethod
    def medical_document_ids(db,person_id):
        from app.models import MedicalDocumentLink,PersonDocument
        return set(db.scalars(select(MedicalDocumentLink.document_id).join(PersonDocument,PersonDocument.id==MedicalDocumentLink.document_id).where(PersonDocument.person_id==person_id)))

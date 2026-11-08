"""One shared effective-source predicate for tables, pickers and assignment writes."""
from datetime import date
from sqlalchemy import and_,or_,exists,select
from app.models.organization import OrgUnit
from app.models.organization_staff import OrgCoverage,OrgStaffImport,OrgStaffImportRow,OrgReassignment
from app.models.reference_book import Position
from app.models.staff import StaffStructure,StaffVersion,PersonAssignment

def effective_position(on,position=Position):
    covered=exists().where(OrgCoverage.org_unit_id==position.org_unit_id,OrgCoverage.staff_version_id==position.staff_version_id,
        OrgCoverage.annulled_at.is_(None),OrgCoverage.valid_from<=on,or_(OrgCoverage.valid_to.is_(None),OrgCoverage.valid_to>=on))
    living=exists().where(OrgUnit.id==position.org_unit_id,OrgUnit.annulled_at.is_(None),OrgUnit.formed_on<=on,or_(OrgUnit.dissolved_on.is_(None),OrgUnit.dissolved_on>=on))
    return and_(position.annulled_at.is_(None),or_(position.valid_from.is_(None),position.valid_from<=on),
        or_(position.valid_to.is_(None),position.valid_to>=on),or_(position.org_unit_id.is_(None),and_(covered,living)))

class OrganizationStaffRepository:
    @staticmethod
    def units(db,ids):return list(db.scalars(select(OrgUnit).where(OrgUnit.id.in_(ids))))
    @staticmethod
    def position_ids(db,unit_ids,version_ids):
        return list(db.scalars(select(Position.position_id).where(Position.org_unit_id.in_(unit_ids),Position.staff_version_id.in_(version_ids),Position.annulled_at.is_(None))))
    @staticmethod
    def linked_positions(db,unit_id):
        return list(db.scalars(select(Position).where(or_(Position.org_unit_id==unit_id,Position.managed_unit_id==unit_id),Position.annulled_at.is_(None))))
    @staticmethod
    def unmapped_for_owners(db,owners,on):
        return db.query(Position.position_id).join(StaffVersion).join(StaffStructure).filter(
            StaffStructure.org_unit_id.in_(owners),StaffVersion.annulled_at.is_(None),StaffVersion.valid_from<=on,
            or_(StaffVersion.valid_to.is_(None),StaffVersion.valid_to>=on),Position.annulled_at.is_(None),Position.org_unit_id.is_(None)).first()
    @staticmethod
    def coverages(db,unit_ids=None):
        q=db.query(OrgCoverage).filter(OrgCoverage.annulled_at.is_(None))
        return (q.filter(OrgCoverage.org_unit_id.in_(unit_ids)) if unit_ids is not None else q).order_by(OrgCoverage.valid_from,OrgCoverage.id).all()
    @staticmethod
    def scoped(db):return db.query(OrgCoverage.id).filter(OrgCoverage.annulled_at.is_(None)).first() is not None
    @staticmethod
    def position_at(db,key,on):return db.query(Position).filter(Position.position_id==key,effective_position(on)).first()
    @staticmethod
    def positions(db,unit_ids,on):
        return db.query(Position).join(StaffVersion).filter(Position.org_unit_id.in_(unit_ids),StaffVersion.valid_from<=on,or_(StaffVersion.valid_to.is_(None),StaffVersion.valid_to>=on),effective_position(on)).order_by(Position.position_number).all()
    @staticmethod
    def version_positions(db,key):return db.query(Position).filter(Position.staff_version_id==key,Position.annulled_at.is_(None)).order_by(Position.position_number).all()
    @staticmethod
    def structure(db,unit_id):return db.query(StaffStructure).filter_by(org_unit_id=unit_id).one_or_none()
    @staticmethod
    def affected_assignments(db,position_ids,start=None):
        q=db.query(PersonAssignment).filter(PersonAssignment.staff_position_id.in_(position_ids),PersonAssignment.annulled_at.is_(None))
        if start is not None:q=q.filter(or_(PersonAssignment.assigned_to.is_(None),PersonAssignment.assigned_to>=start))
        return q.order_by(PersonAssignment.id).all()
    @staticmethod
    def receipt(db,identity):return db.query(OrgStaffImport).filter_by(identity_key=identity).one_or_none()
    @staticmethod
    def rows(db,key):return db.query(OrgStaffImportRow).filter_by(import_id=key).order_by(OrgStaffImportRow.row_number).all()
    @staticmethod
    def receipts(db):return db.query(OrgStaffImport).order_by(OrgStaffImport.id.desc()).limit(100).all()
    @staticmethod
    def queue(db,import_id=None):
        q=db.query(OrgReassignment).filter(OrgReassignment.resolved_assignment_id.is_(None))
        if import_id is not None:q=q.filter_by(import_id=import_id)
        return q.order_by(OrgReassignment.id).all()
    @staticmethod
    def all_structures(db):return db.query(StaffStructure).order_by(StaffStructure.id).all()
    @staticmethod
    def all_versions(db):return db.query(StaffVersion).order_by(StaffVersion.valid_from.desc(),StaffVersion.id).all()
    @staticmethod
    def unbound_positions(db):return db.query(Position).filter(Position.org_unit_id.is_(None),Position.annulled_at.is_(None)).order_by(Position.staff_version_id,Position.position_number).all()
    @staticmethod
    def unbound_structure_at(db,on):
        return db.query(StaffStructure.id).join(StaffVersion).join(Position).filter(
            StaffStructure.org_unit_id.is_(None),StaffVersion.annulled_at.is_(None),
            StaffVersion.valid_from<=on,or_(StaffVersion.valid_to.is_(None),StaffVersion.valid_to>=on),
            Position.annulled_at.is_(None)).first()
    @staticmethod
    def queue_details(db,key=None):
        q=db.query(OrgReassignment,PersonAssignment).join(PersonAssignment,PersonAssignment.id==OrgReassignment.assignment_id).filter(OrgReassignment.resolved_assignment_id.is_(None))
        return (q.filter(OrgReassignment.import_id==key) if key is not None else q).order_by(OrgReassignment.id).all()

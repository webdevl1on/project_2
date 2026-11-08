"""Organization import receipts and dependency queries; no commit or policy."""
from sqlalchemy import select
from app.database.locking import locked_get
from app.models import Position,StaffVersion,StaffStructure,PersonAssignment
from app.models.organization_staff import OrgCoverage,OrgStaffImport,OrgStaffImportRow,OrgReassignment

class OrganizationImportRepository:
    @staticmethod
    def get(db,model,key):return locked_get(db,model,key)
    @staticmethod
    def add(db,value):db.add(value);return value
    @staticmethod
    def receipt(db,identity):return db.scalar(select(OrgStaffImport).where(OrgStaffImport.identity_key==identity))
    @staticmethod
    def rows(db,key):return list(db.scalars(select(OrgStaffImportRow).where(OrgStaffImportRow.import_id==key).order_by(OrgStaffImportRow.row_number)))
    @staticmethod
    def assignments(db,position_ids,*,include_annulled=False):
        query=select(PersonAssignment).where(PersonAssignment.staff_position_id.in_(position_ids))
        if not include_annulled:query=query.where(PersonAssignment.annulled_at.is_(None))
        return list(db.scalars(query.order_by(PersonAssignment.id)))
    @staticmethod
    def positions(db,version_id):return list(db.scalars(select(Position).where(Position.staff_version_id==version_id,Position.annulled_at.is_(None)).order_by(Position.position_number)))
    @staticmethod
    def coverages(db,unit_ids):return list(db.scalars(select(OrgCoverage).where(OrgCoverage.org_unit_id.in_(unit_ids),OrgCoverage.annulled_at.is_(None))))
    @staticmethod
    def structure(db,owner):return db.scalar(select(StaffStructure).where(StaffStructure.org_unit_id==owner))
    @staticmethod
    def unmapped(db,structure_id):
        return list(db.scalars(select(Position).join(StaffVersion).where(StaffVersion.staff_structure_id==structure_id,Position.org_unit_id.is_(None),Position.annulled_at.is_(None))))
    @staticmethod
    def reassignment_rows(db,key):return list(db.scalars(select(OrgReassignment).where(OrgReassignment.import_id==key)))
    @staticmethod
    def receipt_positions(db,key):
        rows=OrganizationImportRepository.rows(db,key)
        return [OrganizationImportRepository.get(db,Position,row.position_id) for row in rows if row.position_id is not None]
    @staticmethod
    def dependent_receipts(db,key,position_ids,unit_ids):
        positions=set(position_ids);units=set(unit_ids)
        candidates=db.scalars(select(OrgStaffImport).where(OrgStaffImport.id!=key,OrgStaffImport.withdrawn_at.is_(None)))
        return [r.id for r in candidates if positions.intersection(p['id'] for p in r.snapshot.get('source_positions',[]))
                or units.intersection(r.snapshot.get('owner_unit_ids',[]))]

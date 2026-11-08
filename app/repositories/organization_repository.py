"""Organizational persistence; services own authorization and transactions."""
from sqlalchemy import select,text
from app.models.organization import OrgUnit,OrgUnitState,OperationalSubordination,OrgAudit
from app.database.locking import locked_get

class OrganizationRepository:
    @staticmethod
    def lock(db):
        if db.get_bind().dialect.name=='postgresql':
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(current_schema()),hashtext('project2_organization'))"))
    @staticmethod
    def get(db,key):return locked_get(db,OrgUnit,key)
    @staticmethod
    def add(db,value):db.add(value);return value
    @staticmethod
    def units(db):return list(db.scalars(select(OrgUnit).order_by(OrgUnit.sort_order,OrgUnit.id)))
    @staticmethod
    def states(db,key=None):
        query=select(OrgUnitState)
        if key is not None:query=query.where(OrgUnitState.org_unit_id==key)
        return list(db.scalars(query.order_by(OrgUnitState.valid_from,OrgUnitState.id)))
    @staticmethod
    def operational(db):return list(db.scalars(select(OperationalSubordination).order_by(OperationalSubordination.valid_from,OperationalSubordination.id)))
    @staticmethod
    def audits(db,key):return list(db.scalars(select(OrgAudit).where(OrgAudit.org_unit_id==key).order_by(OrgAudit.id)))

    @staticmethod
    def operational_record(db,key):return locked_get(db,OperationalSubordination,key)

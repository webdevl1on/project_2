"""Bounded dictionary reads and person geography persistence; no commits."""
from sqlalchemy import select, or_, exists
from app.models import GeoUnit, GeoAlias, PersonAddress, PersonBirthplace

class GeographyRepository:
    @staticmethod
    def type_details(db, ids):
        from app.models import GeoImportLink
        return list(db.execute(select(GeoImportLink.unit_id, GeoImportLink.details).where(GeoImportLink.unit_id.in_(ids))))

    @staticmethod
    def unit(db, key):
        return db.get(GeoUnit, key)

    @staticmethod
    def search(db, kind, query, parent_id=None):
        # Recursive ancestry scopes settlements even when district/community is omitted.
        stmt = select(GeoUnit).where(GeoUnit.kind == kind)
        if parent_id:
            descendants = select(GeoUnit.id).where(GeoUnit.id == parent_id).cte(recursive=True)
            descendants = descendants.union(select(GeoUnit.id).where(GeoUnit.parent_id == descendants.c.id))
            stmt = stmt.where(GeoUnit.parent_id.in_(select(descendants.c.id)))
        pattern = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(GeoUnit.normalized_name.like(pattern, escape="\\"), exists().where(
            GeoAlias.unit_id == GeoUnit.id, GeoAlias.normalized_name.like(pattern, escape="\\"))))
        return list(db.scalars(stmt.order_by(GeoUnit.name, GeoUnit.id).limit(20)))

    @staticmethod
    def aliases(db, key):
        return list(db.scalars(select(GeoAlias.name).where(GeoAlias.unit_id == key)))

    @staticmethod
    def birthplace(db, person_id):
        return db.scalar(select(PersonBirthplace).where(PersonBirthplace.person_id == person_id))

    @staticmethod
    def addresses(db, person_id):
        return list(db.scalars(select(PersonAddress).where(PersonAddress.person_id == person_id).order_by(PersonAddress.id.desc())))

    @staticmethod
    def add(db, record):
        db.add(record)
        return record

    @staticmethod
    def exact(db, kind, normalized, parent_id=None):
        stmt = select(GeoUnit).where(GeoUnit.kind == kind, or_(
            GeoUnit.normalized_name == normalized,
            exists().where(GeoAlias.unit_id == GeoUnit.id, GeoAlias.normalized_name == normalized)))
        if parent_id:
            descendants = select(GeoUnit.id).where(GeoUnit.id == parent_id).cte(recursive=True)
            descendants = descendants.union(select(GeoUnit.id).where(GeoUnit.parent_id == descendants.c.id))
            stmt = stmt.where(GeoUnit.parent_id.in_(select(descendants.c.id)))
        return list(db.scalars(stmt.limit(2)))  # Two suffice to prove ambiguity.

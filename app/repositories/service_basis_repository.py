"""Persistence only. Callers own transaction boundaries."""
from sqlalchemy import select
from app.models.service_basis import PersonServiceBasis, TccOffice, TccImport
from app.utils.text_search import contains_clause


class ServiceBasisRepository:
    @staticmethod
    def records(db, person_id):
        return list(db.scalars(select(PersonServiceBasis).where(PersonServiceBasis.person_id == person_id)
                               .order_by(PersonServiceBasis.is_current.desc(), PersonServiceBasis.id.desc())))

    @staticmethod
    def get(db, person_id, key):
        return db.scalar(select(PersonServiceBasis).where(PersonServiceBasis.person_id == person_id, PersonServiceBasis.id == key))

    @staticmethod
    def add(db, record):
        db.add(record)
        return record


class TccRepository:
    @staticmethod
    def by_ids(db, keys):
        return {office.id: office for office in db.scalars(select(TccOffice).where(TccOffice.id.in_(keys)))} if keys else {}

    @staticmethod
    def get(db, key):
        return db.get(TccOffice, key)

    @staticmethod
    def find(db, values):
        return db.scalar(select(TccOffice).where(*[
            getattr(TccOffice, key) == values[key] for key in ('normalized_name', 'normalized_region', 'normalized_settlement')]))

    @staticmethod
    def list(db, q='', *, active_only=False, region='', settlement='', offset=0, limit=100):
        query = select(TccOffice)
        if active_only:
            query = query.where(TccOffice.is_active.is_(True))
        if q:
            query = query.where(contains_clause(TccOffice.official_name, q))
        if region:
            query = query.where(TccOffice.normalized_region == region)
        if settlement:
            query = query.where(TccOffice.normalized_settlement == settlement)
        return list(db.scalars(query.order_by(TccOffice.official_name, TccOffice.id).offset(offset).limit(limit)))

    @staticmethod
    def locations(db, field):
        return list(db.scalars(select(field).where(field.is_not(None), TccOffice.is_active.is_(True)).distinct().order_by(field)))

    @staticmethod
    def imported(db, key):
        return db.get(TccImport, key) is not None

    add = staticmethod(ServiceBasisRepository.add)

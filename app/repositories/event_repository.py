"""Event persistence and inclusive calendar-period queries; no commits."""
from sqlalchemy import select, and_, or_
from app.models import PersonEvent, EventType, EventSubtype
from app.database.locking import locked_get


def overlap_conditions(start, end):
    conditions = [or_(PersonEvent.date_end.is_(None), PersonEvent.date_end >= start)]
    if end is not None:
        conditions.append(PersonEvent.date_start <= end)
    return and_(*conditions)


class EventRepository:
    @staticmethod
    def get(db, key):
        return locked_get(db, PersonEvent, key)

    @staticmethod
    def owner_id(db, key):
        return db.scalar(select(PersonEvent.person_id).where(PersonEvent.event_id == key))

    @staticmethod
    def get_type(db, key):
        return db.get(EventType, key)

    @staticmethod
    def get_subtype(db, key):
        return db.get(EventSubtype, key)

    @staticmethod
    def types(db):
        return db.scalars(select(EventType).order_by(EventType.event_type_id)).all()

    @staticmethod
    def subtypes(db):
        return db.scalars(select(EventSubtype).order_by(EventSubtype.event_subtype_id)).all()

    @staticmethod
    def all(db):
        return db.scalars(select(PersonEvent)).all()

    @staticmethod
    def for_person(db, person_id):
        return db.scalars(select(PersonEvent).where(PersonEvent.person_id == person_id)
                          .order_by(PersonEvent.date_start, PersonEvent.event_id)).all()

    @staticmethod
    def conflicts(db, person_id, start, end, exclude=None):
        stmt = select(PersonEvent).where(PersonEvent.person_id == person_id, overlap_conditions(start, end))
        if exclude is not None:
            stmt = stmt.where(PersonEvent.event_id != exclude)
        return db.scalars(stmt.order_by(PersonEvent.date_start, PersonEvent.event_id)
                          .execution_options(populate_existing=True)).all()

    @staticmethod
    def by_date(db, person_id, start, end):
        condition = (and_(PersonEvent.date_start <= start,
                          or_(PersonEvent.date_end.is_(None), PersonEvent.date_end >= start))
                     if end is None else overlap_conditions(start, end))
        return db.scalars(select(PersonEvent).where(PersonEvent.person_id == person_id, condition)
                          .order_by(PersonEvent.date_start.asc())).all()

    @staticmethod
    def for_people(db, person_ids, start, end):
        stmt = select(PersonEvent).where(PersonEvent.person_id.in_(person_ids),
                                        or_(PersonEvent.date_end.is_(None), PersonEvent.date_end >= start))
        if end:
            stmt = stmt.where(PersonEvent.date_start <= end)
        return db.scalars(stmt.order_by(PersonEvent.date_start, PersonEvent.event_id)).all()

    @staticmethod
    def add(db, record):
        db.add(record)

    @staticmethod
    def delete(db, record):
        db.delete(record)

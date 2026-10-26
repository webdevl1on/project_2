"""Event access, preserving the existing overlap boundary semantics."""
from sqlalchemy import select, and_, or_
from app.models import PersonEvent, EventType, EventSubtype


def overlap_conditions(start, end):
    # Keep strict finite boundaries used by the existing event service.
    if end is None:
        return or_(PersonEvent.date_end.is_(None), PersonEvent.date_end > start)
    return or_(and_(PersonEvent.date_end.is_not(None), PersonEvent.date_start < end,
                    PersonEvent.date_end > start),
               and_(PersonEvent.date_end.is_(None), PersonEvent.date_start < end))


class EventRepository:
    @staticmethod
    def get(db, key):
        return db.get(PersonEvent, key)

    @staticmethod
    def get_type(db, key):
        return db.get(EventType, key)

    @staticmethod
    def get_subtype(db, key):
        return db.get(EventSubtype, key)

    @staticmethod
    def types(db):
        return db.scalars(select(EventType)).all()

    @staticmethod
    def all(db):
        return db.scalars(select(PersonEvent)).all()

    @staticmethod
    def for_person(db, person_id):
        return db.scalars(select(PersonEvent).where(PersonEvent.person_id == person_id)
                          .order_by(PersonEvent.date_start.asc())).all()

    @staticmethod
    def conflicts(db, person_id, start, end, exclude=None):
        stmt = select(PersonEvent).where(PersonEvent.person_id == person_id, overlap_conditions(start, end))
        if exclude is not None:
            stmt = stmt.where(PersonEvent.event_id != exclude)
        return db.scalars(stmt.order_by(PersonEvent.date_start.asc())).all()

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

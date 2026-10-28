"""Shared records for profile chronology, mirages and table decorations."""
from sqlalchemy import select
from app.models import PersonServiceHistory,PersonAssignment,Position,PersonName

class ServiceHistoryRepository:
    @staticmethod
    def independent(db,person_id):
        return list(db.scalars(select(PersonServiceHistory).where(PersonServiceHistory.person_id==person_id)))

    @staticmethod
    def historical(db,key):
        return db.get(PersonServiceHistory,key)

    @staticmethod
    def add(db,record):
        db.add(record);return record

    @staticmethod
    def assignment(db,key):
        return db.get(PersonAssignment,key)

    @staticmethod
    def mirage(db,key):
        from app.models import PersonPositionMirage
        return db.get(PersonPositionMirage,key)

    @staticmethod
    def mirages(db,person_id=None,position_ids=None):
        from app.models import PersonPositionMirage
        query=select(PersonPositionMirage,Position).join(Position,Position.position_id==PersonPositionMirage.staff_position_id)
        if person_id is not None:query=query.where(PersonPositionMirage.person_id==person_id)
        if position_ids is not None:query=query.where(PersonPositionMirage.staff_position_id.in_(position_ids),PersonPositionMirage.status=='waiting')
        return list(db.execute(query.order_by(PersonPositionMirage.id)))

    @staticmethod
    def waiting(db,person_id):
        from app.models import PersonPositionMirage
        return db.scalar(select(PersonPositionMirage).where(PersonPositionMirage.person_id==person_id,PersonPositionMirage.status=='waiting'))

from app import models
from sqlalchemy import select


class CommonEventFunc:

    #Get list of all person's events
    @staticmethod
    def get_all_person_event(person_id,db):
        stmt = select(models.PersonEvent).filter(
            models.PersonEvent.person_id == person_id).order_by(
                models.PersonEvent.date_start.asc()
            )
        return db.scalars(stmt).all()  

    #Check event_id, if no person raise ERROR
    @staticmethod
    def get_event_or_raise(event_id, db):
        event = db.query(models.PersonEvent).filter(models.PersonEvent.event_id == event_id).first()
        if not event:
            raise ValueError(f"Event with id {event_id} does not exist!")
        return event
    
    #Check event_id(type), if wrong raise ERROR
    @staticmethod
    def get_event_type_or_raise(event_type_id, db):
        event_type = db.query(models.EventType).filter(
            models.EventType.event_type_id == event_type_id
        ).first()
        if not event_type:
            raise ValueError(f"Event type with id {event_type_id} does not exist.")
        return event_type
    
    #Check sub_event_id(type), if wrong raise ERROR
    @staticmethod
    def get_event_subtype_or_raise(event_subtype_id, db):
        event_subtype = db.query(models.EventSubtype).filter(
            models.EventSubtype.event_subtype_id == event_subtype_id
        ).first()
        if not event_subtype:
            raise ValueError(f"Event subtype with id {event_subtype_id} does not exist.")
        return event_subtype
    
    #Check sub_event belongs to event
    @staticmethod
    def validate_event_subtype_belongs_to_type(event_type,event_subtype):
        if event_subtype is None:
            return 
        if event_subtype.event_type_id != event_type.event_type_id:
            raise ValueError(
            f"Event subtype {event_subtype.event_subtype_name} "
            f"does not belong to event type {event_type.event_name}")
from datetime import datetime,date
from app.database.db import SessionLocal    
from app import models
from app.validators.event_validatotor import EventValidator


class PersonEventService:
    @staticmethod
    def get_person_or_raise(person_id, db):
        person = db.query(models.Person).filter(
            models.Person.person_id == person_id
        ).first()
        if not person:
            raise ValueError(f"Person with id {person_id} does not exist.")
        return person
    
    @staticmethod
    def get_event_type_or_raise(event_type_id, db):
        event_type = db.query(models.EventType).filter(
            models.EventType.event_type_id == event_type_id
        ).first()
        if not event_type:
            raise ValueError(f"Event type with id {event_type_id} does not exist.")
        return event_type_id
    @staticmethod
    def get_event_subtype_or_raise(event_subtype_id, db):
        event_subtype = db.query(models.EventSubtype).filter(
            models.EventSubtype.event_subtype_id == event_subtype_id
        ).first()
        if not event_subtype:
            raise ValueError(f"Event subtype with id {event_subtype_id} does not exist.")
        return event_subtype_id
    @staticmethod
    def get_all_person_event(person_id,db):
        return db.query(models.PersonEvent).filter(
            models.PersonEvent.person_id == person_id).all()
       
    @staticmethod
    def create_person_event(
        person_id,
        event_type_id,
        event_subtype_id=None,
        date_start=None,
        duration=None,
        date_end=None,
        order_date=None,
        order_number=None,
        purpose=None,
        location=None,
        note=None,
        event_status=None
    ):
        db = SessionLocal()
        person = PersonEventService.get_person_or_raise(person_id,db)
        person_events = PersonEventService.get_all_person_event(person_id,db)
        event_type = PersonEventService.get_event_type_or_raise(event_type_id,db)
        event_subtype = PersonEventService.get_event_subtype_or_raise(event_subtype_id,db) if event_subtype_id else None
        try:

            person_event = models.PersonEvent(
               

                person_id=person.person_id,
          

                event_type_id=event_type.event_type_id,

                event_subtype_id=event_subtype.event_subtype_id if event_subtype else None,

                date_start=EventValidator.validate_event_date(
                    date_start
                ),

                duration=EventValidator.validate_event_duration(
                    duration
                ),

                date_end=EventValidator.validate_event_date(
                    date_end
                ),

                order_date=EventValidator.validate_event_date(
                    order_date
                ),

                order_number=order_number.strip() if order_number else None,

                purpose=purpose.strip() if purpose else None,

                location=EventValidator.validate_event_location(
                    location
                ),

                note=EventValidator.validate_event_note(
                    note
                ),

                event_status=event_status.strip() if event_status else None
            )

            db.add(person_event)
            db.commit()
            db.refresh(person_event)

            return person_event

        finally:
            db.close()
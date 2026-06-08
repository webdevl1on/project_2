from datetime import datetime, date, timedelta
from sqlalchemy import select, or_
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
    def get_conflicting_events(person_id, date_start, date_end, db):
        stmt = db.select(models.PersonEvent).where(
            models.PersonEvent.person_id == person_id,
            or_(
                models.PersonEvent.date_end >= date_start, 
                models.PersonEvent.date_end.is_(None),
                models.PersonEvent.date_start >= date_start
            )
        ).order_by(models.PersonEvent.date_start.asc())
        return db.scalars(stmt).all()
    @staticmethod
    def process_event_creation(person_id, date_start, date_end, db):
        all_events = PersonEventService.get_all_person_event(person_id, date_start, date_end, db)

        hard_conflicts = []
        future_events = []
        open_active_events = None
        for event in all_events:
            # Old event that start earlier than new event and has no end date
            if event.date_start <= date_start and event.date_end is None:
                open_active_events = event
            # Old event that start earlier than new event and end after new event start date
            elif event.date_start <= date_start and event.date_end >= date_start:
                hard_conflicts.append(event)
            elif event.date_start >= date_start:
                future_events.append(event)
        # main logic for handling conflicts
        if hard_conflicts:
            raise ValueError(
                f"New event conflicts with existing events: {[e.event_id for e in hard_conflicts]}"
            )   
            #if new event has no end date, and it's start date is before start date of future event, then it's a conflict
        if open_active_events:
            open_active_events.date_end = date_start - timedelta(days=1)
        if date_end is None and future_events:
            first_future_event = future_events[0]
            date_end = first_future_event.date_start - timedelta(days=1)
            print(f"New event has no end date, setting end date to {date_end} to avoid conflict with future event {first_future_event.event_id}")
        new_event = models.PersonEvent(
            person_id=person_id,
            date_start=date_start,
            date_end=date_end
        )


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
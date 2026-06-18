from asyncio import Condition
from datetime import datetime, date, timedelta
from sqlalchemy import select, or_, and_
from app.database.db import SessionLocal    
from app import models
from app.validators.event_validatotor import EventValidator


class PersonEventService:
    #Check person_id, if no person raise ERROR
    @staticmethod
    def get_person_or_raise(person_id, db):
        person = db.query(models.Person).filter(
            models.Person.person_id == person_id
        ).first()
        if not person:
            raise ValueError(f"Person with id {person_id} does not exist.")
        return person
    #Check event_id(type), if wrong raise ERROR
    @staticmethod
    def get_event_type_or_raise(event_type_id, db):
        event_type = db.query(models.EventType).filter(
            models.EventType.event_type_id == event_type_id
        ).first()
        if not event_type:
            raise ValueError(f"Event type with id {event_type_id} does not exist.")
        return event_type_id
    #Check sub_event_id(type), if wrong raise ERROR
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
        stmt = db.select(models.PersonEvent).filter(
            models.PersonEvent.person_id == person_id).order_by(
                models.PersonEvent.date_start.asc()
            )
        return db.scalars(stmt).all()
       
    @staticmethod
    def get_conflicting_events(person_id, date_start, date_end, db):
        conditions = [models.PersonEvent.person_id == person_id]
        if date_end is None:
            conditions.append(
                or_(
                    models.PersonEvent.date_end.is_(None),
                    models.PersonEvent.date_end > date_start
                )
            )
        else:
            conditions.append(
                or_(
                    and_(
                        models.PersonEvent.date_end.is_not(None),
                        models.PersonEvent.date_start < date_end,
                        models.PersonEvent.date_end > date_start
                    ),
                    and_(
                        models.PersonEvent.date_end.is_(None),
                        models.PersonEvent.date_start < date_end
                    )
                )
            )
        stmt = (
                select(models.PersonEvent)
                .where(and_(*conditions))
                .order_by(models.PersonEvent.date_start.asc()))
        return db.scalars(stmt).all()
        
   
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

                event_status=event_status.strip() if event_status else None,
                 
            )
            if person_event.duration is not None and person_event.date_end is not None:
                if (person_event.date_end - person_event.date_start).days+1 != person_event.duration: 
                    raise ValueError("Incorrect duration and end date")
            elif person_event.duration is not None and person_event.date_end is None:
                person_event.date_end = person_event.date_start + timedelta(days=person_event.duration-1)
            conflicts = PersonEventService.get_conflicting_events(person_id, person_event.date_start, person_event.date_end, db)
            if conflicts:
                return conflicts
            db.add(person_event)
            db.commit()
            db.refresh(person_event)

            return person_event

        finally:
            db.close()
    
    @staticmethod
    def change_person_event(
        event_id,
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
        pass
    
    @staticmethod
    def delete_person_event():
        pass
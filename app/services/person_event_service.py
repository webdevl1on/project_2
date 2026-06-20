from ast import stmt
from asyncio import Condition
from datetime import datetime, date, timedelta
from sqlalchemy import select, or_, and_
from app.database.db import SessionLocal    
from app import models
from app.services.service_validator_person import PersonService
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
    @staticmethod
    def get_all_person_event(person_id,db):
        stmt = db.select(models.PersonEvent).filter(
            models.PersonEvent.person_id == person_id).order_by(
                models.PersonEvent.date_start.asc()
            )
        return db.scalars(stmt).all()  
    @staticmethod
    def get_conflicting_events(person_id, date_start, date_end, db, exclude_event_id=None):
        conditions = [models.PersonEvent.person_id == person_id]
        if exclude_event_id is not None:
            conditions.append(models.PersonEvent.event_id ==exclude_event_id)
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
        conflicts =db.scalars(stmt).all()
        return conflicts

    @staticmethod
    def compare_date_end_and_duration(person_event):
        if person_event.duration is not None and person_event.date_end is not None:
            if (person_event.date_end - person_event.date_start).days+1 != person_event.duration: 
                raise ValueError("Incorrect duration and end date")
        elif person_event.duration is not None and person_event.date_end is None:
            person_event.date_end = person_event.date_start + timedelta(days=person_event.duration-1)  

    @staticmethod
    def prepare_new_person_event(
        event_type,
        event_subtype=None,
        date_start=None,
        duration=None,
        date_end=None,
        order_date=None,
        order_number=None,
        purpose=None,
        location=None,
        note=None,
        event_status=None):
        
        person_event = models.PersonEvent(
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
        return person_event
       
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
        try:
            person = PersonEventService.get_person_or_raise(person_id,db)
            event_type = PersonEventService.get_event_type_or_raise(event_type_id,db)
            event_subtype = PersonEventService.get_event_subtype_or_raise(event_subtype_id,db) if event_subtype_id else None
            PersonEventService.validate_event_subtype_belongs_to_type(
                event_type,
                event_subtype)
            person_event = PersonEventService.prepare_new_person_event(
                    event_type,
                    event_subtype,
                    date_start,
                    duration,
                    date_end,
                    order_date,
                    order_number,
                    purpose,
                    location,
                    note,
                    event_status)
            person_event = models.PersonEvent(
                person_id = person.person_id
            )
            PersonEventService.compare_date_end_and_duration(person_event)
            conflicts = PersonEventService.get_conflicting_events(person_id, person_event.date_start, person_event.date_end, db)
            if conflicts:
                return conflicts
            db.add(person_event)
            db.commit()
            db.refresh(person_event)
            db.close()
            return person_event
        finally:
            db.close
        
    
    @staticmethod
    def change_person_event(
        event_id,
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
        person_event_old = PersonEventService.get_event_or_raise(event_id, db)
        event_type = PersonEventService.get_event_type_or_raise(event_type_id,db)
        event_subtype = PersonEventService.get_event_subtype_or_raise(event_subtype_id,db) if event_subtype_id else None
        PersonEventService.validate_event_subtype_belongs_to_type(
            event_type,
            event_subtype
        )
        person_event_new = PersonEventService.prepare_new_person_event(
            event_type,
            event_subtype,
            date_start,
            duration,
            date_end,
            order_date,
            order_number,
            purpose,
            location,
            note,
            event_status
        )
        person_event_new.person_id = person_event_old.person_id
        PersonEventService.compare_date_end_and_duration(person_event_new)
        conflicts = PersonEventService.get_conflicting_events(
            person_event_new.person_id, 
            person_event_new.date_start,
            person_event_new.date_end,
            db,
            person_event_old.event_id)
        if conflicts:
            return conflicts
        person_event_old.event_type_id = person_event_new.event_type_id
        person_event_old.event_subtype_id = person_event_new.event_subtype_id
        person_event_old.date_start = person_event_new.date_start
        person_event_old.duration = person_event_new.duration
        person_event_old.date_end = person_event_new.date_end
        person_event_old.order_date = person_event_new.order_date
        person_event_old.order_number = person_event_new.order_number
        person_event_old.purpose = person_event_new.purpose
        person_event_old.location = person_event_new.location
        person_event_old.note = person_event_new.note
        person_event_old.event_status = person_event_new.event_status
        db.commit()
        db.refresh(person_event_old)
        db.close()
        return person_event_old


        
    @staticmethod
    def get_person_event_by_date(person_id: int, date_start: str, date_end: str | None = None, duration: str | None = None,):
        db = SessionLocal()
        try:
            PersonEventService.get_person_or_raise(person_id, db)
            start_date=EventValidator.validate_event_date(date_start)
            assert start_date is not None
            end_date=EventValidator.validate_event_date(date_end)
            duration_days=EventValidator.validate_event_duration(duration)
            if duration_days is not None and end_date is not None:
                if (end_date - start_date).days+1 != duration_days: 
                    raise ValueError("Incorrect duration and end date")
            elif duration_days is not None and end_date is None:
                end_date = start_date + timedelta(days=duration_days-1)  
            conditions = [models.PersonEvent.person_id == person_id]
            if end_date is None:
                conditions.append(
                    and_(
                        models.PersonEvent.date_start <= start_date,
                        or_(
                            models.PersonEvent.date_end.is_(None),
                            models.PersonEvent.date_end >= start_date
                        )
                    )
                )
            else:
                if start_date > end_date: 
                    raise ValueError("start_date cannot be bigger then end_date")
                conditions.append(
                or_(
                    and_(
                        models.PersonEvent.date_end.is_not(None),
                        models.PersonEvent.date_start < end_date,
                        models.PersonEvent.date_end > start_date
                    ),
                    and_(
                        models.PersonEvent.date_end.is_(None),
                        models.PersonEvent.date_start < end_date
                    )
                )
            )
            stmt = select(models.PersonEvent).where(*conditions).order_by(models.PersonEvent.date_start.asc())
            events = db.scalars(stmt).all()  
            return events 
        finally:
            db.close()
    
    @staticmethod
    def delete_person_event(event_id, db):
        stmt = select(models.PersonEvent).where(models.PersonEvent.event_id == event_id)
        event = db.scalars(stmt).first()
        if event:
            db.delete(event)
            db.commit()
            return True
        return False
        
from datetime import timedelta
from app.database.transactions import session_scope
from app.repositories.event_repository import EventRepository
from app import models
from app.services.service_person_checking import ServicePersonCheck
from app.services.service_common_event_func import CommonEventFunc
from app.validators.event_validatotor import EventValidator


class PersonEventService:
    """Event rules; db= joins the caller's transaction without committing it.

    Standalone calls retain the session_factory API. A conflicting create/edit
    still returns the existing event list instead of saving a new state.
    """

    @staticmethod
    def get_conflicting_events(person_id, date_start, date_end, db, exclude_event_id=None):
        return EventRepository.conflicts(db, person_id, date_start, date_end, exclude_event_id)

    @staticmethod
    def compare_date_end_and_duration(person_event):
        if person_event.date_end is not None and person_event.date_end < person_event.date_start:
            raise ValueError("Дата завершення не може передувати початку.")
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
                date_start, required=True
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
        event_status=None,
        *, db=None, session_factory=None
    ):
        with session_scope(db, session_factory=session_factory, write=True) as db:
            person = ServicePersonCheck.get_person_or_raise(person_id,db)
            event_type = CommonEventFunc.get_event_type_or_raise(event_type_id,db)
            event_subtype = CommonEventFunc.get_event_subtype_or_raise(event_subtype_id,db) if event_subtype_id else None
            CommonEventFunc.validate_event_subtype_belongs_to_type(
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
            person_event.person_id = person.person_id
            PersonEventService.compare_date_end_and_duration(person_event)
            conflicts = PersonEventService.get_conflicting_events(person_id, person_event.date_start, person_event.date_end, db)
            if conflicts:
                return conflicts
            EventRepository.add(db, person_event)
            db.flush()
            db.refresh(person_event)
            return person_event

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
        event_status=None,
        *, db=None, session_factory=None
    ):
        with session_scope(db, session_factory=session_factory, write=True) as db:
            person_event_old = CommonEventFunc.get_event_or_raise(event_id, db)
            event_type = CommonEventFunc.get_event_type_or_raise(event_type_id,db)
            event_subtype = CommonEventFunc.get_event_subtype_or_raise(event_subtype_id,db) if event_subtype_id else None
            CommonEventFunc.validate_event_subtype_belongs_to_type(
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
            db.flush()
            db.refresh(person_event_old)
            return person_event_old

    @staticmethod
    def get_person_event_by_date(person_id: int, date_start: str, date_end: str | None = None, duration: str | None = None, *, db=None, session_factory=None):
        with session_scope(db, session_factory=session_factory) as db:
            ServicePersonCheck.get_person_or_raise(person_id, db)
            start_date=EventValidator.validate_event_date(date_start)
            assert start_date is not None
            end_date=EventValidator.validate_event_date(date_end)
            duration_days=EventValidator.validate_event_duration(duration)
            if duration_days is not None and end_date is not None:
                if (end_date - start_date).days+1 != duration_days:
                    raise ValueError("Incorrect duration and end date")
            elif duration_days is not None and end_date is None:
                end_date = start_date + timedelta(days=duration_days-1)
            if end_date is not None and start_date > end_date:
                raise ValueError("start_date cannot be bigger then end_date")
            return EventRepository.by_date(db, person_id, start_date, end_date)

    @staticmethod
    def delete_person_event(event_id, *, db=None, session_factory=None):
        with session_scope(db, session_factory=session_factory, write=True) as db:
            event = EventRepository.get(db, event_id)
            if event:
                EventRepository.delete(db, event)
                return True
            return False

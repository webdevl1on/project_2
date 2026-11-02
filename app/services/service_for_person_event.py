from datetime import timedelta
from app.database.transactions import session_scope
from app.repositories.event_repository import EventRepository
from app import models
from app.services.staff_service import today
from app.services.event_rules import confirmation_required, planned
from app.services.service_person_checking import ServicePersonCheck
from app.services.service_common_event_func import CommonEventFunc
from app.validators.event_validatotor import EventValidator


class EventValidationError(ValueError):
    def __init__(self, message, field):
        super().__init__(message)
        self.field = field


def exact_date(value, field, *, required=False):
    try:
        return EventValidator.validate_event_date(value, required=required)
    except ValueError as error:
        raise EventValidationError(str(error), field) from error


def duration_days(value):
    try:
        return EventValidator.validate_event_duration(value)
    except (ValueError, TypeError, OverflowError) as error:
        raise EventValidationError('Тривалість має бути додатним цілим числом днів.', 'duration') from error


class PersonEventService:
    """Event rules; db= joins the caller's transaction without committing it.

    Standalone calls retain the session_factory API. A conflicting create/edit
    returns the complete conflict list without saving a partial state. Only a
    single previous open conflict may be closed atomically during creation.
    """

    @staticmethod
    def get_conflicting_events(person_id, date_start, date_end, db, exclude_event_id=None):
        return EventRepository.conflicts(db, person_id, date_start, date_end, exclude_event_id)

    @staticmethod
    def compare_date_end_and_duration(person_event):
        if person_event.date_end is not None and person_event.date_end < person_event.date_start:
            raise EventValidationError("Дата завершення не може бути раніше дати початку.", "date_end")
        if person_event.duration is not None and person_event.date_end is not None:
            if (person_event.date_end - person_event.date_start).days+1 != person_event.duration:
                raise EventValidationError("Тривалість не відповідає датам початку та завершення (обидві дати включні).", "duration")
        elif person_event.duration is not None and person_event.date_end is None:
            try:
                person_event.date_end = person_event.date_start + timedelta(days=person_event.duration-1)
            except (OverflowError, ValueError) as error:
                raise EventValidationError("Тривалість виходить за допустимий календарний період.", "duration") from error
        if person_event.date_end is not None:
            person_event.duration = (person_event.date_end - person_event.date_start).days + 1

    @staticmethod
    def lifecycle(record, planned_end, planned_duration, confirmed):
        record.planned_end = exact_date(planned_end, 'planned_end')
        if planned_duration not in ('', None):
            try:
                days = duration_days(planned_duration)
                calculated = record.date_start + timedelta(days=days-1)
            except (ValueError, TypeError, OverflowError) as error:
                raise EventValidationError('Орієнтовна тривалість має бути додатним числом у межах календаря.', 'planned_duration') from error
            if record.planned_end and calculated != record.planned_end:
                raise EventValidationError('Орієнтовна тривалість не відповідає плановій даті.', 'planned_duration')
            record.planned_end = calculated
        if record.planned_end and record.planned_end < record.date_start:
            raise EventValidationError('Орієнтовне завершення не може бути раніше початку.', 'planned_end')
        # Legacy callers explicitly supplying actual end/duration keep that contract.
        record.completion_confirmed = record.date_end is not None if confirmed is None else confirmed
        if not isinstance(record.completion_confirmed, bool):
            raise EventValidationError('Некоректна ознака підтвердження.', 'completion_confirmed')
        if record.completion_confirmed and not record.date_end:
            raise EventValidationError('Укажіть фактичну дату підтвердженого завершення.', 'date_end')
        if record.date_end and not record.completion_confirmed:
            raise EventValidationError('Фактичне завершення потребує явного підтвердження. Планову дату внесіть окремо.', 'completion_confirmed')
        if record.completion_confirmed and record.date_end > today():
            raise EventValidationError('Не можна підтвердити завершення в майбутньому.', 'date_end')

    @staticmethod
    def period_conflicts(record, db, exclude=None):
        # Future plans may overlap facts, never silently close them. Once their
        # start arrives, an unresolved overlap is visible and requires a decision.
        if planned(record):
            candidates = EventRepository.for_person(db, record.person_id)
            return [r for r in candidates if r.event_id != exclude and planned(r) and
                    (record.planned_end is None or r.date_start <= record.planned_end) and
                    (r.planned_end is None or r.planned_end >= record.date_start)]
        conflicts = PersonEventService.get_conflicting_events(record.person_id, record.date_start, record.date_end, db, exclude)
        return [r for r in conflicts if not planned(r)]

    @staticmethod
    def validate_catalog(event_type, event_subtype, previous=None):
        if not event_type.event_is_active and (previous is None or previous.event_type_id != event_type.event_type_id):
            raise EventValidationError("Цей тип події неактивний. Оберіть активний тип.", "event_type_id")
        try:
            CommonEventFunc.validate_event_subtype_belongs_to_type(event_type, event_subtype)
        except ValueError as error:
            # Retain the established diagnostic for non-HTTP service callers.
            raise EventValidationError("Підтип не належить обраному типу події (does not belong).", "event_subtype_id") from error
        if event_subtype and not event_subtype.event_subtype_is_active and (previous is None or previous.event_subtype_id != event_subtype.event_subtype_id):
            raise EventValidationError("Цей підтип неактивний. Оберіть активний підтип.", "event_subtype_id")

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
            date_start=exact_date(date_start, "date_start", required=True),
            duration=duration_days(duration),
            date_end=exact_date(date_end, "date_end"),
            order_date=exact_date(order_date, "order_date"),
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
        *, db=None, session_factory=None, planned_end=None, planned_duration=None, completion_confirmed=None
    ):
        with session_scope(db, session_factory=session_factory, write=True) as db:
            person = ServicePersonCheck.get_person_or_raise(person_id,db)
            event_type = CommonEventFunc.get_event_type_or_raise(event_type_id,db)
            event_subtype = CommonEventFunc.get_event_subtype_or_raise(event_subtype_id,db) if event_subtype_id else None
            PersonEventService.validate_catalog(event_type, event_subtype)
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
            PersonEventService.lifecycle(person_event, planned_end, planned_duration, completion_confirmed)
            conflicts = PersonEventService.period_conflicts(person_event, db)
            if conflicts:
                # Inspect ALL conflicts before changing the previous record.
                # Finite conflicts, equal/later starts or ambiguous open history
                # must never be silently rewritten.
                if len(conflicts) != 1 or conflicts[0].date_end is not None or conflicts[0].date_start >= person_event.date_start:
                    return conflicts
                previous = conflicts[0]
                previous_type = EventRepository.get_type(db, previous.event_type_id)
                if planned(person_event) or confirmation_required(previous_type.event_type):
                    return conflicts
                previous_end = person_event.date_start - timedelta(days=1)
                historical_conflicts = EventRepository.conflicts(db, person.person_id, previous.date_start, previous_end, previous.event_id)
                if historical_conflicts:
                    return [previous, *historical_conflicts]
                previous.date_end = previous_end
                previous.duration = (previous.date_end - previous.date_start).days + 1
                previous.completion_confirmed = True
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
        *, db=None, session_factory=None, planned_end=None, planned_duration=None, completion_confirmed=None
    ):
        with session_scope(db, session_factory=session_factory, write=True) as db:
            owner = EventRepository.owner_id(db, event_id)
            if owner is None:
                raise ValueError("Подію не знайдено.")
            # Always lock Person before an event, matching creation lock order.
            ServicePersonCheck.get_person_or_raise(owner, db)
            person_event_old = CommonEventFunc.get_event_or_raise(event_id, db)
            event_type = CommonEventFunc.get_event_type_or_raise(event_type_id,db)
            event_subtype = CommonEventFunc.get_event_subtype_or_raise(event_subtype_id,db) if event_subtype_id else None
            PersonEventService.validate_catalog(event_type, event_subtype, person_event_old)
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
            PersonEventService.lifecycle(person_event_new, planned_end, planned_duration, completion_confirmed)
            conflicts = PersonEventService.period_conflicts(person_event_new, db, person_event_old.event_id)
            if conflicts:
                return conflicts
            person_event_old.planned_end = person_event_new.planned_end
            person_event_old.completion_confirmed = person_event_new.completion_confirmed
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

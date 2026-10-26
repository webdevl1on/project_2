from app.repositories.event_repository import EventRepository


class CommonEventFunc:

    #Get list of all person's events
    @staticmethod
    def get_all_person_event(person_id,db):
        return EventRepository.for_person(db, person_id)

    #Check event_id, if no person raise ERROR
    @staticmethod
    def get_event_or_raise(event_id, db):
        event = EventRepository.get(db, event_id)
        if not event:
            raise ValueError(f"Event with id {event_id} does not exist!")
        return event

    #Check event_id(type), if wrong raise ERROR
    @staticmethod
    def get_event_type_or_raise(event_type_id, db):
        event_type = EventRepository.get_type(db, event_type_id)
        if not event_type:
            raise ValueError(f"Event type with id {event_type_id} does not exist.")
        return event_type

    #Check sub_event_id(type), if wrong raise ERROR
    @staticmethod
    def get_event_subtype_or_raise(event_subtype_id, db):
        event_subtype = EventRepository.get_subtype(db, event_subtype_id)
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

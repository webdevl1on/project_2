"""Explicit read-only diagnostic command; importing performs no database IO."""
from app.database.transactions import session_scope
from app.repositories.event_repository import EventRepository


def main():
    with session_scope() as db:
        for event in EventRepository.all(db):
            print(f"Event ID: {event.event_id}, Person ID: {event.person_id}, Event Type ID: {event.event_type_id}, "
                  f"Event Subtype ID: {event.event_subtype_id}, Date Start: {event.date_start}, Duration: {event.duration}, "
                  f"Date End: {event.date_end}, Order Date: {event.order_date}, Order Number: {event.order_number}, "
                  f"Purpose: {event.purpose}, Location: {event.location}, ------------")


if __name__ == "__main__":
    main()

"""Explicit read-only diagnostic command; importing performs no database IO."""
from app.database.transactions import session_scope
from app.repositories.event_repository import EventRepository


def main():
    with session_scope() as db:
        rows = EventRepository.types(db)

        print("COUNT =", len(rows))

        for row in rows:
            print(
                row.event_type_id,
                row.event_type,
                row.event_name
            )


if __name__ == "__main__":
    main()

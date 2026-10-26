"""Transaction boundaries shared by services, never by repositories."""
from contextlib import contextmanager

from app.database.db import SessionLocal


@contextmanager
def service_transaction(db, *, commit=True, immediate=False):
    """Own a complete operation, or participate in a caller-owned transaction.

    With commit=False the caller must commit/rollback the entire unit, including
    after validation or flush failures. Never commit unrelated pending writes.
    Staff writes keep their stronger BEGIN IMMEDIATE boundary in write_unit.
    """
    if commit and (db.new or db.dirty or db.deleted):
        raise ValueError("Спочатку завершіть поточні незбережені зміни.")
    if immediate and not commit:
        raise ValueError("Блокування запису потребує власної транзакції.")
    try:
        if immediate:
            db.rollback()
            if db.get_bind().dialect.name == "sqlite":
                db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield db
        db.flush()
        if commit:
            db.commit()
    except Exception:
        if commit:
            db.rollback()
        raise


@contextmanager
def session_scope(db=None, *, session_factory=None, write=False):
    """Borrow without closing/committing, or own a legacy standalone session."""
    if db is not None and session_factory is not None:
        raise ValueError("Передайте сесію або фабрику сесій, не обидві одночасно.")
    owned = db is None
    session = (session_factory or SessionLocal)() if owned else db
    if owned and write:
        # Standalone services return loaded ORM data after closing their session,
        # as the former commit/refresh/close implementation did.
        session.expire_on_commit = False
    try:
        if write:
            with service_transaction(session, commit=owned):
                yield session
        else:
            yield session
    finally:
        if owned:
            session.close()

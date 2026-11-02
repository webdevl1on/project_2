"""Immutable snapshots and correction metadata; no transaction ownership."""
from datetime import date, datetime, UTC
from app.repositories.event_repository import EventRepository as Repo
from app.models import PersonEventCorrection


def snapshot(row):
    result = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    result = {key: value.isoformat() if isinstance(value, (date, datetime)) else value for key, value in result.items()}
    return result


def capture(db, row):
    result = snapshot(row)
    kind, sub = Repo.get_type(db, row.event_type_id), Repo.get_subtype(db, row.event_subtype_id) if row.event_subtype_id else None
    return {**result, 'type_name': kind.event_name, 'subtype_name': sub.event_subtype_name if sub else None}


def record(db, row, operation, before, actor_id):
    db.add(PersonEventCorrection(event_id=row.event_id, actor_id=actor_id, operation=operation,
                                 before=before, after=capture(db, row)))


def utc_text(value):
    if value is None: return None
    return value.replace(tzinfo=UTC).isoformat()


def history(db, person_id):
    result = {}
    for row, name in Repo.corrections(db, person_id):
        result.setdefault(row.event_id, []).append({'id': row.id, 'operation': row.operation,
            'actor_id': row.actor_id, 'actor_name': name, 'occurred_at': utc_text(row.occurred_at),
            'before': row.before, 'after': row.after})
    return result

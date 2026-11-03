"""Audit writes belong to the caller's personnel transaction; never commit here."""
from datetime import date, datetime
from app.models.assignment_audit import AssignmentAudit

FIELDS = ('person_id','staff_position_id','assigned_from','assigned_to',
          'assignment_order_number','assignment_order_date','release_order_number',
          'release_order_date','completion_reason','completion_note',
          'annulled_at','annulment_reason','annulled_by','revision')


def snapshot(record):
    return {key: value.isoformat() if isinstance(value, (date, datetime)) else value
            for key in FIELDS for value in [getattr(record, key)]}


def record_change(db, record, operation, before=None, actor_id=None, reason=None):
    db.flush()
    after = snapshot(record)
    before = before or {}
    if before == after: return
    db.add(AssignmentAudit(assignment_id=record.id, actor_user_id=actor_id,
                          operation=operation, before=before, after=after, reason=reason))
    db.flush()  # audit failure rolls back the entire write_unit

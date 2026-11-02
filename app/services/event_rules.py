"""Personnel event rules only; never reads or modifies medical tasks."""
from datetime import date
from app.services.staff_service import today

AUTO_CLOSE_TYPES = frozenset({'SERVICE', 'DUTY', 'DAY_OFF'})
PROBLEM_GROUPS = {'rotation': 'Ротації / СБЗ', 'vacation': 'Відпустки', 'hospital': 'Лікарняні', 'vlk': 'ВЛК', 'other': 'Інші події'}


def planned(record, on=None):
    return record.date_start > (on or today())


def confirmation_required(code):
    return code not in AUTO_CLOSE_TYPES


def problem(record, *, on=None):
    """Stable single issue per event, calculated from current dates, no daily rows."""
    on = on or today()
    start = date.fromisoformat(record['date_start'])
    if start > on or record['completion_confirmed'] or record.get('annulled_at'):
        return None
    end = date.fromisoformat(record['planned_end']) if record['planned_end'] else None
    code, subtype = record['type_code'], record.get('subtype_code')
    overdue = end is not None and on > end
    group, reason = None, None
    if code == 'BUSINESS_TRIP' and subtype == 'BUSINESS_TRIP_MISSION' and end and (end-on).days <= 20:
        group, reason = 'rotation', 'Контроль завершення СБЗ'
    elif code == 'VACATION' and overdue:
        group, reason = 'vacation', 'Повернення з відпустки не підтверджене'
    elif (code == 'VLK' or subtype in {'VLK', 'HOSPITAL_VLK'}) and (on-start).days >= 15:
        group, reason = 'vlk', 'Перебування на ВЛК понад 15 календарних днів'
    elif code == 'HOSPITAL' and (on-start).days >= 15:
        group, reason = 'hospital', 'Лікування понад 15 календарних днів'
    elif overdue:
        group, reason = 'other', 'Потребує підтвердження завершення'
    if reason:
        return {'id': f"event:{record['event_id']}", 'event_id': record['event_id'], 'person_id': record['person_id'],
                'group': group, 'group_label': PROBLEM_GROUPS[group], 'reason': reason, 'overdue': overdue,
                'planned_end': record['planned_end'], 'type_name': record['type_name'], 'period': record['period']}
    return None

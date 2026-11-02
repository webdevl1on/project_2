"""Person-event editor contract; mutations delegate to PersonEventService."""
from hashlib import sha256
from datetime import date
from app.services.staff_service import today
import json
import re
from app.repositories.event_repository import EventRepository as Repo
from app.services.service_for_person_event import PersonEventService, EventValidationError, exact_date
from app.services.service_person_checking import ServicePersonCheck
from app.database.transactions import service_transaction

FIELDS = ('event_type_id', 'event_subtype_id', 'date_start', 'date_end', 'duration',
          'order_date', 'order_number', 'purpose', 'location', 'note', 'event_status', 'planned_end', 'completion_confirmed')


class EventConflictError(ValueError):
    field = 'date_start'

    def __init__(self, conflicts, message=None, field='date_start'):
        super().__init__(message or 'Період перетинається з іншими подіями. Перевірте наведені записи та виправте дати.')
        self.conflicts = conflicts
        self.field = field


def day_label(value):
    return f'{value.day:02d}.{value.month:02d}.{value.year:04d}'


def serialize(row, types, subtypes):
    values = {field: getattr(row, field) for field in FIELDS}
    for field in ('date_start', 'date_end', 'order_date', 'planned_end'):
        values[field] = values[field].isoformat() if values[field] else None
    kind, subtype = types[row.event_type_id], subtypes.get(row.event_subtype_id)
    identity = {'event_id': row.event_id, 'person_id': row.person_id, **values}
    return {**identity, 'type_name': kind.event_name, 'type_code': kind.event_type,
            'subtype_name': subtype.event_subtype_name if subtype else None,
            'subtype_code': subtype.event_subtype if subtype else None,
            'subtype_tint': (.30 + .24 * (sorted(s.event_subtype_id for s in subtypes.values() if s.event_type_id == row.event_type_id).index(row.event_subtype_id)+1) / (1+sum(s.event_type_id == row.event_type_id for s in subtypes.values()))) if subtype else .22,
            'type_color': kind.event_color,
            'mirage': row.date_start > today(),
            'legacy_future_end': bool(row.date_end and row.date_end > today() and not row.completion_confirmed),
            'period': day_label(row.date_start) + ' — ' + (day_label(row.date_end) if row.date_end else 'заплановано' if row.date_start > today() else 'по сьогодні'),
            # Optimistic editor snapshot without inventing a database revision.
            'expected_state': sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()}


def dictionaries(db):
    return ({row.event_type_id: row for row in Repo.types(db)},
            {row.event_subtype_id: row for row in Repo.subtypes(db)})


def page(db, person_id):
    ServicePersonCheck.get_person_or_raise(person_id, db)
    types, subtypes = dictionaries(db)
    return {'person_id': person_id, 'today': today().isoformat(),
            'types': [{'id': kind.event_type_id, 'code': kind.event_type, 'name': kind.event_name,
                       'color': kind.event_color, 'active': bool(kind.event_is_active),
                       'exclusive': bool(kind.event_exclusive),
                       'subtypes': [{'id': sub.event_subtype_id, 'code': sub.event_subtype,
                                     'name': sub.event_subtype_name, 'active': bool(sub.event_subtype_is_active)}
                                    for sub in subtypes.values() if sub.event_type_id == kind.event_type_id]}
                      for kind in types.values()],
            'events': [serialize(row, types, subtypes) for row in reversed(Repo.for_person(db, person_id))]}


def identifier(value, field, *, optional=False):
    if optional and value in ('', None):
        return None
    try:
        number = int(value)
        if number < 1 or isinstance(value, bool):
            raise ValueError()
        return number
    except (ValueError, TypeError, OverflowError) as error:
        raise EventValidationError('Оберіть коректне значення з довідника.', field) from error


def save(db, person_id, data, key=None):
    fields = {field: data.get(field) for field in FIELDS}
    for field in ('date_start', 'date_end', 'order_date', 'planned_end'):
        raw = fields[field]
        # Native HTML dates use ISO; the legacy event validator keeps its DMY
        # contract. Convert only a complete ISO date at this UI boundary.
        if isinstance(raw, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw):
            try:
                fields[field] = date.fromisoformat(raw)
            except ValueError as error:
                raise EventValidationError('Потрібна точна календарна дата.', field) from error
        else:
            fields[field] = exact_date(raw, field, required=field == 'date_start')
    for field in ('event_type_id', 'event_subtype_id'):
        fields[field] = identifier(fields[field], field, optional=field == 'event_subtype_id')
    raw_confirmation = fields['completion_confirmed']
    if raw_confirmation not in (None, '', '0', '1', 'false', 'true', False, True):
        raise EventValidationError('Некоректна ознака підтвердження.', 'completion_confirmed')
    fields['completion_confirmed'] = None if raw_confirmation is None else raw_confirmation in ('1', 'true', True)
    fields['planned_duration'] = data.get('planned_duration')
    # Own one complete transaction; nested event calls borrow it without commit.
    with service_transaction(db, immediate=True):
        ServicePersonCheck.get_person_or_raise(person_id, db)
        types, subtypes = dictionaries(db)
        if fields['event_type_id'] not in types:
            raise EventValidationError('Тип події не знайдено.', 'event_type_id')
        if fields['event_subtype_id'] is not None and fields['event_subtype_id'] not in subtypes:
            raise EventValidationError('Підтип події не знайдено.', 'event_subtype_id')
        if key is not None:
            old = Repo.get(db, key)
            if old is None or old.person_id != person_id:
                raise ValueError('Подію цієї людини не знайдено.')
            if data.get('expected_state') != serialize(old, types, subtypes)['expected_state']:
                raise EventConflictError([serialize(old, types, subtypes)],
                                         'Подію вже змінено. Перевірте актуальний запис і відкрийте його для редагування знову.', None)
            result = PersonEventService.change_person_event(key, **fields, db=db)
        else:
            result = PersonEventService.create_person_event(person_id, **fields, db=db)
        if isinstance(result, list):
            raise EventConflictError([serialize(row, types, subtypes) for row in result])
        result_id = result.event_id
    return result_id

"""Validated, revision-checked atomic profile edits, reusing personnel audit."""
from app.models.profile_records import MODELS
from app.profile_records import FIELDS, LABELS
from app.repositories.profile_record_repository import ProfileRecordRepository as Repo
from app.services.accounts import authorize
from app.services.documents import document_transaction, WRITE_ROLES, _text
from app.services.medical import exact, snapshot, audit
from app.services import geography
from app.geography import GEO_FIELDS

GEO_IDS = {key+'_id' for key in (*GEO_FIELDS, 'street')}


def subject(db, person_id, kind):
    if kind not in MODELS:
        raise ValueError('Невідомий розділ анкети.')
    if Repo.person(db, person_id) is None:
        raise ValueError('Особу не знайдено.')


def validate(db, kind, data):
    allowed = {field[0] for field in FIELDS[kind]} | (GEO_IDS if kind == 'family' else set())
    if not isinstance(data, dict) or set(data) - allowed:
        raise ValueError('Некоректні або невідомі поля запису.')
    values = {}
    for key, label, control, options, required in FIELDS[kind]:
        value = data.get(key)
        try:
            if control == 'date':
                value = exact(value)
            elif control == 'select':
                if value not in options:
                    raise ValueError('виберіть значення зі списку.')
            elif key == 'address_text':
                if value is not None and (not isinstance(value, str) or len(value) > options or any(ord(c) < 32 and c not in '\r\n\t' for c in value)):
                    raise ValueError(f'потрібен текст до {options} символів.')
                value = value if value and value.strip() else None
            else:
                value = _text(value, options)
            if required and not value:
                raise ValueError('поле обов’язкове.')
        except ValueError as error:
            raise ValueError(f'{label}: {error}') from None
        values[key] = value
    if kind == 'education' and values['started_on'] and values['ended_on'] and values['ended_on'] < values['started_on']:
        raise ValueError('Дата закінчення не може бути раніше дати початку.')
    warnings = []
    if kind == 'directives' and not (values['number'] or values['issued_on']):
        raise ValueError('Вкажіть номер або точну дату розпорядження.')
    if kind == 'family':
        if values['birth_on'] and values['death_on'] and values['death_on'] < values['birth_on']:
            raise ValueError('Дата смерті не може бути раніше дати народження.')
        # Same verifier, no inferred IDs or mandatory geography. Original text is independent.
        keys = {key for key, _, control, _, _ in FIELDS[kind] if control == 'geo' or key in ('settlement_type','street_type','house','corps','building','apartment','room')}
        if any(values[key] for key in keys - {'settlement_type','street_type'}):
            prepared, warnings = geography.prepare(db, {**{key:values[key] for key in keys}, **{key:data.get(key) for key in GEO_IDS}})
            values.update({key:value for key,value in prepared.items() if key in keys | GEO_IDS | {'validation_status'}})
        else:
            values.update({key:None for key in GEO_IDS})
            values['validation_status'] = 'unknown'
            if values['address_text'] or any(data.get(key) for key in GEO_IDS):
                warnings.append('Довільна адреса збережена без підтвердження географічним довідником.')
    return values, warnings


def save(db, actor_id, person_id, kind, data, *, key=None, revision=None):
    with document_transaction(db, subject='запису анкети'):
        authorize(db, actor_id, WRITE_ROLES)
        subject(db, person_id, kind)
        if key is not None:
            row = Repo.get(db, kind, key)
            if row is None or row.person_id != person_id:
                raise ValueError('Запис цієї особи не знайдено.')
            if revision is None or str(revision) != str(row.revision):
                raise ValueError('Запис уже змінено; оновіть список. Чернетку збережено.')
            old = snapshot(row)
        else:
            row = MODELS[kind](person_id=person_id)
            old = {}
        values, warnings = validate(db, kind, data)
        for field, value in values.items():
            setattr(row, field, value)
        Repo.add(db, row)
        db.flush()
        audit(db, actor_id, person_id, kind, row, 'update' if key is not None else 'create', old)
        result = {'id': row.id, 'revision': row.revision, 'warnings': warnings}
    return result


def page(db, actor_id, person_id, kind):
    user = authorize(db, actor_id)
    subject(db, person_id, kind)
    return {'title': LABELS[kind], 'role': user.role, 'fields': FIELDS[kind],
            'records': [{**snapshot(row), 'created_at': row.created_at.isoformat()+'Z',
                         'updated_at': row.updated_at.isoformat()+'Z'} for row in Repo.rows(db, kind, person_id)],
            'audit': [{'actor_id': row.actor_id, 'operation': row.operation, 'entity_id': row.entity_id,
                       'occurred_at': row.occurred_at.isoformat()+'Z', 'changes': row.changes}
                      for row in Repo.audits(db, kind, person_id)]}

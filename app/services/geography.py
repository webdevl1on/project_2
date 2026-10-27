"""Soft geographic verification, immutable address history and formatting."""
from datetime import date
from app.geography import GEO_FIELDS, DETAIL_FIELDS, ADDRESS_TYPES, SETTLEMENT_TYPES, STREET_TYPES, SETTLEMENT_TYPE_ALIASES, normalize
from app.utils.address_format import format_address
from app.geography import BIRTH_COMPONENTS, ADDRESS_COMPONENTS, EMPTY_GEO_MESSAGES
from app.models import PersonAddress, PersonBirthplace
from app.repositories.geography_repository import GeographyRepository as Repo
from app.services.service_person_checking import ServicePersonCheck
from app.database.transactions import service_transaction


def suggestions(db, kind, query, parent_id=None):
    if kind not in (*GEO_FIELDS, 'street'):
        raise ValueError('Невідомий тип географічного поля.')
    query = normalize(query)
    if len(query) < 2:
        return []
    if len(query) > 250:
        raise ValueError('Пошуковий запит надто довгий.')
    rows = Repo.search(db, kind, query, parent_id)
    types = {}
    if rows and kind in ('settlement', 'street'):
        for unit_id, details in Repo.type_details(db, [r.id for r in rows]):
            raw = (details or {}).get(kind + '_type')
            if not isinstance(raw, str) or not raw.strip():
                continue
            raw = SETTLEMENT_TYPE_ALIASES.get(raw, raw) if kind == 'settlement' else raw
            types.setdefault(unit_id, set()).add(raw)
    return [{'id': r.id, 'name': r.name, 'parent_id': r.parent_id,
             'context': context(db, r),
             'type': next(iter(types[r.id])) if len(types.get(r.id, ())) == 1 else None} for r in rows]


def context(db, unit):
    names = []; seen = {unit.id}
    while unit.parent_id and len(names) < 6:
        unit = Repo.unit(db, unit.parent_id)
        if not unit or unit.id in seen:
            break
        seen.add(unit.id); names.append(unit.name)
    return ', '.join(reversed(names))


def prepare(db, data, *, birth=False):
    fields = list(GEO_FIELDS) + ['settlement_type'] + ([] if birth else list(DETAIL_FIELDS))
    values = {}; warnings = []; selected = {}; mismatch = False
    for key in fields:
        raw = data.get(key) or ''
        limit = 1000 if key == 'note' else 60 if key == 'settlement_type' else 250
        if not isinstance(raw, str) or len(raw) > limit:
            raise ValueError(f'{key}: допускається до {limit} символів.')
        values[key] = raw.strip() or None
    meaningful = BIRTH_COMPONENTS if birth else ADDRESS_COMPONENTS
    if not any(values[key] for key in meaningful):
        raise ValueError(EMPTY_GEO_MESSAGES['birthplace' if birth else 'address'])
    for key in list(GEO_FIELDS) + ([] if birth else ['street']):
        raw = data.get(key + '_id')
        unit = None
        if raw:
            try:
                unit = Repo.unit(db, int(raw))
            except (ValueError, TypeError):
                pass
            if not unit or unit.kind != key:
                warnings.append(f'{GEO_FIELDS.get(key, "Вулиця")}: довідникове посилання недоступне; текст збережено.')
                mismatch = True; unit = None
        values[key + '_id'] = unit.id if unit else None
        if unit:
            selected[key] = unit
            if normalize(values[key]) not in {normalize(n) for n in [unit.name, *Repo.aliases(db, unit.id)]}:
                mismatch = True
                warnings.append(f'{GEO_FIELDS.get(key, "Вулиця")}: текст відрізняється від довідника; запропоновано «{unit.name}».')
        elif values[key]:
            candidates = Repo.search(db, key, normalize(values[key]))
            exact = [u for u in candidates if normalize(u.name) == normalize(values[key])]
            for candidate in exact[:3]:
                ancestors = set(); current = candidate
                while current.parent_id and current.parent_id not in ancestors:
                    ancestors.add(current.parent_id); current = Repo.unit(db, current.parent_id)
                    if not current: break
                if any(parent.kind != key and parent.id not in ancestors for parent in selected.values()):
                    mismatch = True
                    warnings.append(f'{GEO_FIELDS.get(key, "Вулиця")}: можливий збіг «{candidate.name}» ({context(db, candidate)}); перевірте вручну.')
    units = list(selected.values())
    for child in units:
        ancestors = set(); current = child
        while current.parent_id and current.parent_id not in ancestors:
            ancestors.add(current.parent_id); current = Repo.unit(db, current.parent_id)
            if not current: break
        order = list(GEO_FIELDS) + ['street']
        for parent in units:
            if order.index(parent.kind) < order.index(child.kind) and parent.id not in ancestors:
                mismatch = True
                warnings.append(f'Невідповідність: «{child.name}» не належить до «{parent.name}». Варіант довідника: {context(db, child) or child.name}.')
    if not birth:
        country = selected.get('country')
        ukrainian = normalize(values['country']) in {'україна', 'украина', 'ukraine'} or bool(country and country.iso_code == 'UA')
        postal = values['postal_code']
        if ukrainian and postal and (len(postal) != 5 or not postal.isascii() or not postal.isdigit()):
            raise ValueError('Для України поштовий індекс має містити п’ять цифр.')
        for key in ('date_start', 'date_end'):
            raw = data.get(key)
            try:
                values[key] = date.fromisoformat(raw) if raw else None
            except (ValueError, TypeError):
                raise ValueError('Період адреси потребує повної дати у форматі РРРР-ММ-ДД.') from None
        if values['date_start'] and values['date_end'] and values['date_end'] < values['date_start']:
            raise ValueError('Дата завершення не може бути раніше дати початку.')
    provided = [key for key in list(GEO_FIELDS) + ([] if birth else ['street']) if values[key]]
    values['validation_status'] = 'mismatch' if mismatch else 'matched' if provided and all(key in selected for key in provided) else 'unknown'
    if values['validation_status'] == 'unknown':
        warnings.append('Довідник не підтверджує всі компоненти. Ручне введення дозволено.')
    return values, warnings


def save(db, person_id, block, data, *, commit=True):
    birth = block == 'birthplace'
    if not birth and block not in ADDRESS_TYPES:
        raise ValueError('Невідомий тип адреси.')
    with service_transaction(db, commit=commit, immediate=commit):
        ServicePersonCheck.get_person_or_raise(person_id, db)
        values, warnings = prepare(db, data, birth=birth)
        old = Repo.birthplace(db, person_id) if birth else next((r for r in Repo.addresses(db, person_id) if r.kind == block and r.is_active), None)
        expected = str(old.revision) if old else ''
        if str(data.get('revision') or '') != expected or str(data.get('record_id') or '') != (str(old.id) if old else ''):
            raise ValueError('Дані вже змінені. Оновіть блок перед збереженням; введений текст залишено у формі.')
        if birth:
            record = old or Repo.add(db, PersonBirthplace(person_id=person_id))
        else:
            if old:
                old.is_active = False
                db.flush()
            record = Repo.add(db, PersonAddress(person_id=person_id, kind=block))
        for key, value in values.items():
            setattr(record, key, value)
    return warnings


def page(db, person_id):
    ServicePersonCheck.get_person_or_raise(person_id, db)
    records = Repo.addresses(db, person_id)
    blocks = {'birthplace': Repo.birthplace(db, person_id)}
    blocks.update({kind: next((r for r in records if r.kind == kind and r.is_active), None) for kind in ADDRESS_TYPES})
    return {'birth_components': BIRTH_COMPONENTS, 'address_components': ADDRESS_COMPONENTS, 'empty_geo_messages': EMPTY_GEO_MESSAGES, 'person_id': person_id, 'geo_blocks': blocks, 'geo_history': [r for r in records if not r.is_active],
            'geo_fields': GEO_FIELDS, 'detail_fields': DETAIL_FIELDS,
            'settlement_types': SETTLEMENT_TYPES, 'street_types': STREET_TYPES, 'address_types': ADDRESS_TYPES, 'format_address': format_address}

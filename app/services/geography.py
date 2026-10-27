"""Soft geographic verification, immutable address history and formatting."""
import unicodedata
from datetime import date
from app.geography import GEO_FIELDS, DETAIL_FIELDS, ADDRESS_TYPES
from app.models import PersonAddress, PersonBirthplace
from app.repositories.geography_repository import GeographyRepository as Repo
from app.services.service_person_checking import ServicePersonCheck
from app.database.transactions import service_transaction


def normalize(value):
    return ' '.join(unicodedata.normalize('NFC', value or '').casefold().split())


def suggestions(db, kind, query, parent_id=None):
    if kind not in (*GEO_FIELDS, 'street'):
        raise ValueError('Невідомий тип географічного поля.')
    query = normalize(query)
    if len(query) < 2:
        return []
    if len(query) > 250:
        raise ValueError('Пошуковий запит надто довгий.')
    return [{'id': r.id, 'name': r.name, 'parent_id': r.parent_id,
             'context': context(db, r)} for r in Repo.search(db, kind, query, parent_id)]


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


def save(db, person_id, block, data):
    birth = block == 'birthplace'
    if not birth and block not in ADDRESS_TYPES:
        raise ValueError('Невідомий тип адреси.')
    with service_transaction(db, immediate=True):
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


def format_address(record):
    def value(key):
        return (record.get(key) if isinstance(record, dict) else getattr(record, key, None)) or ''
    settlement = ' '.join(filter(None, [value('settlement_type'), value('settlement')]))
    street = ' '.join(filter(None, [value('street_type'), value('street')]))
    parts = [value(k) for k in ('country','region','district','community')] + [settlement, street]
    for key, label in [('house','буд.'),('corps','корп.'),('building','будівля'),('apartment','кв.'),('room','кімн.')]:
        if value(key): parts.append(f'{label} {value(key)}')
    parts.extend([value('postal_code'), value('note')])
    return ', '.join(filter(None, parts))


def page(db, person_id):
    ServicePersonCheck.get_person_or_raise(person_id, db)
    records = Repo.addresses(db, person_id)
    blocks = {'birthplace': Repo.birthplace(db, person_id)}
    blocks.update({kind: next((r for r in records if r.kind == kind and r.is_active), None) for kind in ADDRESS_TYPES})
    return {'person_id': person_id, 'geo_blocks': blocks, 'geo_history': [r for r in records if not r.is_active],
            'geo_fields': GEO_FIELDS, 'detail_fields': DETAIL_FIELDS,
            'address_types': ADDRESS_TYPES, 'format_address': format_address}

"""Read-only journal and date-specific staff presence; events remain person-owned."""
from collections import Counter, defaultdict
from datetime import date, timedelta
from app.repositories.event_repository import EventRepository as Repo
from app.repositories.person_repository import PersonRepository
from app.services.staff_service import today
from app.services.person_events import serialize, day_label
from app.event_display import presentation, legend, event_presentation
from app.services import event_rules

MONTHS = ('січ', 'лют', 'бер', 'кві', 'тра', 'чер', 'лип', 'сер', 'вер', 'жов', 'лис', 'гру')
WEEKDAYS = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд')


def state_on(events, on):
    iso = on.isoformat()
    active = [r for r in events if r['date_start'] <= iso and (r['date_end'] is None or r['date_end'] >= iso)]
    unresolved = [r for r in events if r['date_start'] <= iso and not r['completion_confirmed'] and
                  ((r['planned_end'] and r['planned_end'] < iso) or (r['date_end'] and r['date_end'] < iso))]
    if len(active) > 1 or (unresolved and any(r['event_id'] not in {e['event_id'] for e in unresolved} for r in active)):
        result = presentation('__conflict__')
    elif unresolved:
        result = presentation('__pending__')
        if len(unresolved) == 1:
            result.update(event_type_name=unresolved[0]['type_name'], subtype=unresolved[0]['subtype_name'])
    elif active:
        result = event_presentation(active[0])
    else:
        result = presentation()
    relevant = {r['event_id']: r for r in [*active, *unresolved]}
    result.update(event_ids=list(relevant), mirage=any(r['mirage'] for r in active),
                  description='; '.join(r['type_name'] + (' · ' + r['subtype_name'] if r['subtype_name'] else '') + ': ' + r['period'] +
                  ('; орієнтовно до ' + day_label(date.fromisoformat(r['planned_end'])) if r['planned_end'] else '') for r in relevant.values()) or result['name'])
    if unresolved: result['description'] += '; завершення не підтверджене'
    if result['mirage']: result['description'] = 'Міраж (план). ' + result['description']
    return result


def presence(events, *, vacant=False, on=None):
    return {**presentation('__vacant__'), 'event_ids': []} if vacant else state_on(events, on or today())


def records(db, start, end, ids=None):
    rows = Repo.window_rows(db, start, end, ids)
    kinds = {kind.event_type_id: kind for _, kind, _ in rows}
    subs = {sub.event_subtype_id: sub for _, _, sub in rows if sub is not None}
    return [serialize(row, kinds, subs) for row, _, _ in rows]


def presence_for_people(db, ids, on):
    grouped = defaultdict(list)
    if ids:
        for row in records(db, on, on, ids): grouped[row['person_id']].append(row)
    return {pid: presence(grouped[pid], on=on) for pid in ids}


def parse_options(raw):
    def exact(key, fallback):
        value = raw.get(key)
        try:
            if not value: return fallback
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value: raise ValueError()
            return parsed
        except (ValueError, TypeError): raise ValueError('Період має містити повні календарні дати РРРР-ММ-ДД.') from None
    end = exact('end', today())
    start = exact('start', end - timedelta(days=min(13, end.toordinal()-1)))
    if start > end: raise ValueError('Завершення періоду не може передувати початку.')
    if (end-start).days >= 366: raise ValueError('Оберіть період не більше 366 днів.')
    scale = raw.get('scale', 'day')
    if scale not in ('day', 'week', 'month'): raise ValueError('Невідомий масштаб журналу.')
    search = (raw.get('search') or '').strip()
    unit = raw.get('unit') or ''
    if len(search) > 250 or len(unit) > 250: raise ValueError('Надто довге значення фільтра.')
    try:
        kind = int(raw['event_type']) if raw.get('event_type') else None
        if kind is not None and kind < 1: raise ValueError()
    except (ValueError, TypeError): raise ValueError('Некоректний тип події.') from None
    sort = raw.get('sort', 'name')
    if sort not in ('name', 'unit'): raise ValueError('Невідоме сортування журналу.')
    direction = raw.get('direction', 'asc')
    if direction not in ('asc', 'desc'): raise ValueError('Невідомий напрямок сортування.')
    return {'start': start, 'end': end, 'scale': scale, 'search': search, 'unit': unit,
            'event_type': kind, 'sort': sort, 'direction': direction}


def buckets(start, end, scale):
    result = []
    cursor = start
    while cursor <= end:
        if scale == 'day': finish = cursor
        elif scale == 'week': finish = min(end, cursor + timedelta(days=min(6-cursor.weekday(), date.max.toordinal()-cursor.toordinal())))
        else:
            finish = min(end, date(cursor.year+1, 1, 1)-timedelta(days=1) if cursor.month == 12 and cursor.year < 9999 else
                         date(cursor.year, cursor.month+1, 1)-timedelta(days=1) if cursor.month < 12 else date.max)
        result.append({'start': cursor.isoformat(), 'end': finish.isoformat(),
                       'label': f'{cursor.day:02d}' if scale == 'day' else f'{cursor.day:02d}–{finish.day:02d}' if scale == 'week' else MONTHS[cursor.month-1],
                       'month': MONTHS[cursor.month-1], 'weekday': WEEKDAYS[cursor.weekday()],
                       'weekend': cursor.weekday() >= 5, 'period': day_label(cursor) + ' — ' + day_label(finish)})
        if finish == date.max: break
        cursor = finish + timedelta(days=1)
    return result



def calendar_projection(events, periods, types):
    """Project each date once; base service, unconfirmed ends and plans are distinct."""
    all_counts, cells = Counter(), []
    for bucket in periods:
        counts, states, ids = Counter(), [], set()
        day, finish = date.fromisoformat(bucket['start']), date.fromisoformat(bucket['end'])
        while day <= finish:
            state = state_on(events, day)
            states.append(state); counts[state['code']] += 1; ids.update(state['event_ids'])
            if day == date.max: break
            day += timedelta(days=1)
        all_counts.update(counts)
        same = len({(r['code'], r.get('subtype'), r.get('mirage')) for r in states}) == 1
        cell = dict(states[0]) if same else {**presentation('__mixed__', 'Різні події'), 'label': f'{len(counts)} стани'}
        if same and len(states) > 1: cell['label'] += f' · {len(states)}'
        cell['description'] = bucket['period'] + ': ' + '; '.join(dict.fromkeys(r['description'] for r in states))
        cell['event_ids'] = sorted(ids); cell['mirage'] = any(r.get('mirage') for r in states)
        cells.append(cell)
    names = {t.event_type: t.event_name for t in types.values()}
    wanted = [r['code'] for r in legend() if r['code'] != '__vacant__']
    keys = list(dict.fromkeys([*wanted, *all_counts]))
    return cells, [{**presentation(key, names.get(key)), 'days': all_counts[key]} for key in keys]


def problems(db, on=None):
    on = on or today()
    rows = Repo.problem_rows(db, on)
    types = {kind.event_type_id: kind for _, kind, _ in rows}
    subs = {sub.event_subtype_id: sub for _, _, sub in rows if sub}
    names = {p.person_id: ' '.join(v for v in (name.surname, name.name, name.patronymic) if v) if name else 'Без ПІБ'
             for p, name, *_ in PersonRepository.picker_rows(db, on)}
    items = []
    for row, _, _ in rows:
        item = event_rules.problem(serialize(row, types, subs), on=on)
        if item: items.append({**item, 'person_name': names.get(row.person_id, 'Без ПІБ')})
    return {'on': on.isoformat(), 'on_label': day_label(on), 'groups': event_rules.PROBLEM_GROUPS, 'items': items,
            'has_vlk': any(t.event_type == 'VLK' for t in Repo.types(db)) or any(s.event_subtype in {'VLK','HOSPITAL_VLK'} for s in Repo.subtypes(db))}


def journal(db, raw):
    options = parse_options(raw)
    start, end = options['start'], options['end']
    types = Repo.types(db)
    if options['event_type'] is not None and options['event_type'] not in {r.event_type_id for r in types}:
        raise ValueError('Тип події не знайдено.')
    periods = buckets(start, end, options['scale'])
    kinds = {t.event_type_id: t for t in types}
    by_person = defaultdict(list)
    for item in records(db, start, end): by_person[item['person_id']].append(item)
    units = defaultdict(set)
    for pid, unit in Repo.assignment_units(db, start, end):
        if unit: units[pid].add(unit)
    from app.utils.text_search import normalized_text
    from app.utils.date_utils import format_partial_date
    people, seen = [], set()
    for person, name, rank, assignment, position in PersonRepository.picker_rows(db, end):
        if person.person_id in seen: continue
        seen.add(person.person_id)
        pid = person.person_id
        label = ' '.join(v for v in (name.surname, name.name, name.patronymic) if v) if name else 'Без ПІБ'
        available = by_person[pid]
        if options['search'] and normalized_text(options['search']) not in normalized_text(label): continue
        if options['unit'] and options['unit'] not in units[pid]: continue
        if options['event_type'] and not any(r['event_type_id'] == options['event_type'] for r in available): continue
        unit_label = ', '.join(sorted(units[pid])) or 'Без штатного призначення'
        cells, summary = calendar_projection(available, periods, kinds)
        people.append({'cells': cells, 'summary': summary, 'id': pid, 'name': label, 'rank': rank.nominative if rank else 'Звання не зазначено',
                       'birth': format_partial_date(person.birth_day, person.birth_month, person.birth_year),
                       'unit': unit_label, 'units': sorted(units[pid]), 'position_number': position.position_number if position else None,
                       'position_short': position.name_short if position else None, 'events': available})
    people.sort(key=lambda p: ((p['unit'].casefold(), p['name'].casefold(), p['id']) if options['sort'] == 'unit' else
                               (p['name'].casefold(), p['id'])), reverse=options['direction'] == 'desc')
    return {'options': {**options, 'start': start.isoformat(), 'end': end.isoformat()},
            'buckets': periods, 'people': people,
            'types': [{'id': t.event_type_id, 'code': t.event_type, 'name': t.event_name,
                       'active': bool(t.event_is_active), **{'presentation': event_presentation({'type_code': t.event_type, 'type_name': t.event_name, 'type_color': t.event_color})}} for t in types],
            'units': sorted({u for entries in units.values() for u in entries}), 'legend': [p for p in legend() if p['code'] != '__vacant__']}

"""Read-only journal and date-specific staff presence; events remain person-owned."""
from collections import Counter, defaultdict
from datetime import date, timedelta
from app.repositories.event_repository import EventRepository as Repo
from app.repositories.person_repository import PersonRepository
from app.services.staff_service import today
from app.services.person_events import serialize, day_label
from app.event_display import presentation, legend

MONTHS = ('січ', 'лют', 'бер', 'кві', 'тра', 'чер', 'лип', 'сер', 'вер', 'жов', 'лис', 'гру')
WEEKDAYS = ('Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд')


def classification(events):
    return events[0]['event_type_id'] if len(events) == 1 else '__conflict__' if events else None


def presence(events, *, vacant=False):
    key = classification(events)
    if vacant:
        result = presentation('__vacant__')
    elif key == '__conflict__':
        result = presentation('__conflict__')
    elif events:
        result = presentation(events[0]['type_code'], events[0]['type_name'])
    else:
        result = presentation()
    return {**result, 'event_ids': [r['event_id'] for r in events],
            'description': '; '.join(r['type_name'] + ': ' + r['period'] for r in events) or result['name']}


def records(db, start, end, ids=None):
    rows = Repo.window_rows(db, start, end, ids)
    kinds = {kind.event_type_id: kind for _, kind, _ in rows}
    subs = {sub.event_subtype_id: sub for _, _, sub in rows if sub is not None}
    return [serialize(row, kinds, subs) for row, _, _ in rows]


def presence_for_people(db, ids, on):
    grouped = defaultdict(list)
    if ids:
        for row in records(db, on, on, ids): grouped[row['person_id']].append(row)
    return {pid: presence(grouped[pid]) for pid in ids}


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
    """Count calendar days once; simultaneous records become an explicit conflict."""
    all_counts = Counter()
    cells = []
    for bucket in periods:
        counts = Counter()
        ids = set()
        day = date.fromisoformat(bucket['start'])
        finish = date.fromisoformat(bucket['end'])
        while day <= finish:
            iso = day.isoformat()
            active = [item for item in events if item['date_start'] <= iso and (item['date_end'] is None or item['date_end'] >= iso)]
            key = classification(active)
            counts[key] += 1
            ids.update(item['event_id'] for item in active)
            if day == date.max: break
            day += timedelta(days=1)
        all_counts.update(counts)
        entries = [count_entry(key, value, types) for key, value in counts.items()]
        cell = {**entries[0]} if len(entries) == 1 else {**presentation('__mixed__', 'Різні події'), 'label': f'{len(entries)} стани'}
        if len(entries) == 1 and sum(counts.values()) > 1: cell['label'] += f" · {sum(counts.values())}"
        cell['description'] = bucket['period'] + ': ' + '; '.join(f"{r['name']} — {r['days']} дн." for r in entries)
        cell['event_ids'] = sorted(ids)
        cells.append(cell)
    wanted = [t.event_type_id for meta in legend() for t in types.values() if t.event_type == meta['code']]
    keys = list(dict.fromkeys([*wanted, *all_counts, None]))
    return cells, [count_entry(key, all_counts[key], types) for key in keys]


def count_entry(key, days, types):
    kind = types.get(key)
    return {**presentation(kind.event_type if kind else key, kind.event_name if kind else None), 'days': days}


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
                       'unit': unit_label, 'units': sorted(units[pid]), 'events': available})
    people.sort(key=lambda p: ((p['unit'].casefold(), p['name'].casefold(), p['id']) if options['sort'] == 'unit' else
                               (p['name'].casefold(), p['id'])), reverse=options['direction'] == 'desc')
    return {'options': {**options, 'start': start.isoformat(), 'end': end.isoformat()},
            'buckets': periods, 'people': people,
            'types': [{'id': t.event_type_id, 'code': t.event_type, 'name': t.event_name,
                       'active': bool(t.event_is_active), **{'presentation': presentation(t.event_type, t.event_name)}} for t in types],
            'units': sorted({u for entries in units.values() for u in entries}), 'legend': [p for p in legend() if p['code'] != '__vacant__']}

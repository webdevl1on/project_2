"""Read use cases for staff pages, independent of HTTP and Jinja."""
from datetime import date
from app.models import StaffVersion, Position, PersonAssignment
from app.repositories.staff_repository import StaffRepository
from app.services.staff_service import StaffService, today
from app.services.person_picker import person_options
from app.services.assignment_audit import snapshot as assignment_snapshot


def table_context(db, version_id=None, on=None):
    structures = StaffRepository.structures(db, ordered=True)
    versions = StaffRepository.versions(db, stable=True)
    chosen = next((item for item in versions if item.id == version_id), None)
    if version_id is not None and chosen is None:
        raise ValueError("Версія не існує.")
    if chosen is None and structures:
        current = today()
        preferred = sorted(structures, key=lambda item: (item.code != "main", item.code))
        chosen = next((version for structure in preferred for version in versions
                       if version.staff_structure_id == structure.id
                       and version.valid_from <= current <= (version.valid_to or date.max)), None)
    if on is None:
        on = today()
        if chosen:
            on = max(chosen.valid_from, min(on, chosen.valid_to or date.max))
    if chosen and not chosen.valid_from <= on <= (chosen.valid_to or date.max):
        raise ValueError("Дата перегляду не належить періоду версії.")
    return structures, versions, chosen, on


def history_context(db, version_id=None, structure_id=None, search=''):
    versions = StaffRepository.versions(db)
    if structure_id is not None:
        versions = [v for v in versions if v.staff_structure_id == structure_id]
    chosen = next((v for v in versions if v.id == version_id), None) if version_id else (versions[0] if versions else None)
    structures = StaffRepository.structures(db)
    positions = StaffRepository.positions(db, chosen.id) if chosen else []
    records = StaffRepository.assignment_history(db, chosen.id) if chosen else []
    people = person_options(db, today())
    names = {person['id']:person['label'] for person in people}
    groups = {position.position_id:{'position':position,'current':[], 'archive':[], 'future':[], 'annulled':[], 'count':0} for position in positions}
    on = today()
    for record, position in records:
        group = groups[position.position_id]; group['count'] += 1
        bucket = ('annulled' if record.annulled_at else 'future' if record.assigned_from > on
                  else 'current' if record.assigned_to is None or record.assigned_to >= on else 'archive')
        group[bucket].append(record)
    for group in groups.values():
        for bucket in ('current','archive','future','annulled'):
            group[bucket].sort(key=lambda item:(item.assigned_from,item.id), reverse=True)
    query = search.strip().casefold()
    groups = [group for group in groups.values() if not query or any(query in str(value or '').casefold()
              for value in (group['position'].position_number, group['position'].name_short, group['position'].name_nominative))]
    return {'versions':versions,'chosen':chosen,'positions':positions,'records':records,
            'assignment_payloads':{record.id:{**assignment_snapshot(record),'id':record.id,'position_label':f'№{position.position_number} — {position.name_short}','person_label':names.get(record.person_id,'Без ПІБ')} for record,position in records},
            'completion_labels':{'release':'Звільнення з посади','transfer':'Переведення','version_closed':'Закриття версії','other':'Інша причина'},
            'position_groups':groups,'search':search,'people':people,'person_names':names,
            'structures':structures,'structure_names':{item.id:f'{item.name} ({item.code})' for item in structures}}


def assignment_position_id(db, key):
    record=StaffRepository.get(db, PersonAssignment, key)
    if record is None: raise ValueError('Призначення не існує.')
    return record.staff_position_id


def assignment_audit_context(db, key):
    from app.utils.date_utils import format_calendar_date
    assignment_position_id(db, key)
    labels={'person_id':'Військовослужбовець (ID)','staff_position_id':'Посада (ID)',
            'assigned_from':'Початок','assigned_to':'Завершення','assignment_order_number':'Номер наказу призначення',
            'assignment_order_date':'Дата наказу призначення','release_order_number':'Номер наказу завершення',
            'release_order_date':'Дата наказу завершення','completion_reason':'Причина завершення','completion_note':'Примітка',
            'annulled_at':'Час анулювання (UTC)','annulment_reason':'Причина анулювання','annulled_by':'Автор анулювання (ID)'}
    operations={'create':'Створення','edit':'Редагування','orders':'Реквізити наказів','complete':'Завершення',
                'transfer':'Переведення','annul':'Анулювання','restore':'Відновлення'}
    result=[]
    for entry, user in StaffRepository.audit_history(db,key):
        changes=[]
        for field,label in labels.items():
            before=entry.before.get(field);after=entry.after.get(field)
            if before==after: continue
            if field.endswith('_date') or field in ('assigned_from','assigned_to'):
                before=format_calendar_date(before);after=format_calendar_date(after)
            elif field=='annulled_at':
                from datetime import datetime
                from app.utils.date_utils import format_system_timestamp
                before=format_system_timestamp(datetime.fromisoformat(before)) if before else None
                after=format_system_timestamp(datetime.fromisoformat(after)) if after else None
            changes.append((label,before,after))
        result.append({'entry':entry,'actor':(user.display_name or user.username) if user else 'Автор невідомий',
                       'operation':operations[entry.operation],'changes':changes})
    return {'audit_entries':result}


def assignment_preview(db, position_id, person_id, on):
    snapshot = StaffService.assignment_snapshot(db, position_id, person_id, on)
    target = StaffRepository.get(db, Position, position_id)
    source = StaffRepository.get(db, PersonAssignment, snapshot['source'][0]) if snapshot['source'] else None
    previous = StaffRepository.get(db, Position, source.staff_position_id) if source else None
    return snapshot, person_options(db, on), target, source, previous


def position_version_id(db, key):
    return StaffRepository.get(db, Position, key).staff_version_id

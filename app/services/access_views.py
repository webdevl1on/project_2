"""Scoped projections: denied data never reaches HTML, facets, exports or picker JSON."""
from types import SimpleNamespace
from app.services import access
from app.access_catalog import CATEGORIES
from app.repositories.person_repository import PersonRepository,ProfileRepository
from app.repositories.contact_repository import ContactRepository
from app.models import Person
from app.utils.date_utils import format_partial_date


def scoped(db):
    if db.info.get('access_actor') is None:return None
    cached=db.info.get('access_read_evaluator')
    if cached and cached.user.id==db.info['access_actor']:return cached if cached.user.role!='admin' else None
    e=access.Access(db);db.info['access_read_evaluator']=e
    return e if e.user.role!='admin' else None

def field_category(field):
    if field.source=='position':return 'organization'
    if field.data_type=='datetime':return 'history'
    if field.group in ('medical','injuries','awards','tasks','dna'):return 'medical'
    if field.group=='events':return 'events'
    if field.source in ('passport',) or field.key=='tax_number':return 'documents'
    if field.key in ('surname','name','patronymic','full_name','rank'):return 'basic'
    if field.source in ('person_rank','rank','service') or field.group=='service':return 'service'
    return 'personal'

def minimum(db,pid,e):
    if not e.allowed('basic',person_id=pid):return {'id':pid,'name':f'Військовослужбовець ID {pid}','rank':None,'position':None,'phone':None}
    name=PersonRepository.current_name(db,pid);rank=PersonRepository.current_rank(db,pid)
    current=e.current.get(pid);position=e.positions.get(current.staff_position_id) if current else None
    phones=[r for r in ContactRepository.list(db,pid) if r.is_active and r.contact_type=='phone']
    phone=next((r.value for r in phones if r.is_primary),phones[0].value if phones else None)
    return {'id':pid,'name':' '.join(v for v in (name.surname,name.name,name.patronymic) if v) if name else 'ПІБ не зазначено',
            'rank':rank.rank.nominative if rank and rank.rank else None,'position':position.name_short if position else None,'phone':phone}

def people(db,sort_by,direction):
    e=scoped(db)
    if e is None:return None
    rows=[]
    for person,name,rank in PersonRepository.list_people(db,'id','asc'):
        pid=person.person_id
        if not e.allowed('basic',person_id=pid):continue
        personal=e.allowed('personal',person_id=pid);documents=e.allowed('documents',person_id=pid);service=e.allowed('service',person_id=pid)
        safe=SimpleNamespace(person_id=pid,tax_number=person.tax_number if documents else None,**{key:getattr(person,key) if personal else None for key in ('birth_day','birth_month','birth_year')})
        safe_rank=SimpleNamespace(rank=rank.rank,rank_order_number=rank.rank_order_number if service else None) if rank else None
        rows.append({'person':safe,'name':name,'rank':safe_rank})
    def key(row):
        if sort_by=='id':return row['person'].person_id
        if sort_by=='birth_year':return tuple(getattr(row['person'],key) or 0 for key in ('birth_year','birth_month','birth_day'))
        if sort_by=='rank':return (row['rank'].rank.nominative if row['rank'] and row['rank'].rank else '').casefold()
        if sort_by=='tax_number':return row['person'].tax_number or ''
        return (getattr(row['name'],'name' if sort_by=='name' else 'surname',None) or '').casefold()
    return sorted(rows,key=key,reverse=direction=='desc')

def profile(db,pid):
    from app.services import medical,documents,contacts,geography,service_bases,service_chronology
    from app.medical_catalog import FITNESS,FORM_FIELDS,LABELS,DOCUMENT_ROLES
    from app.models import PersonName,PersonRank
    e=access.Access(db);person=PersonRepository.get_by_id(db,pid)
    if person is None:raise ValueError('Особу не знайдено.')
    rights={c:{a:e.allowed(c,a,person_id=pid) for a in ('read','edit')} for c in CATEGORIES}
    if not any(r['read'] for r in rights.values()):raise PermissionError('Доступ відсутній.')
    result={'person_id':pid,'minimum':minimum(db,pid,e),'access_rights':rights,
            'medical_labels':LABELS,'medical_metadata':{'fields':FORM_FIELDS,'labels':LABELS,'documents':DOCUMENT_ROLES,'fitness':FITNESS}}
    result.update(medical_fitness=FITNESS,medical_fields=FORM_FIELDS,medical_documents=DOCUMENT_ROLES)
    if rights['personal']['read']:
        result['personal']={'sex':person.sex,'birth':format_partial_date(person.birth_day,person.birth_month,person.birth_year),'personal_number':person.personal_number}
        result.update(contacts.page(db,pid));result.update(geography.page(db,pid))
    if rights['basic']['read']:result['name_rows']=ProfileRepository.active_records(db,PersonName,pid)
    if rights['service']['read']:
        result['service_chronology']=service_chronology.chronology(db,pid);result.update(service_bases.page(db,pid))
        result['ranks']=PersonRepository.ranks(db);result['person_rank_rows']=ProfileRepository.active_records(db,PersonRank,pid)
    return result


def prune_tree(db,tree):
    e=scoped(db)
    if e is None:return tree
    visible={key for key in e.states if e.allowed('organization',unit_id=key)}
    path=set(visible)
    parents={u['id']:u['parent_id'] for u in tree['units']}
    for key in list(visible):
        parent=parents.get(key);seen=set()
        while parent is not None and parent not in seen:
            seen.add(parent);path.add(parent);parent=parents.get(parent)
    units=[{**u,'children':[key for key in u['children'] if key in path],'context_only':u['id'] not in visible} for u in tree['units'] if u['id'] in path]
    return {**tree,'units':units,'roots':[key for key in tree['roots'] if key in path],'inactive_units':[]}

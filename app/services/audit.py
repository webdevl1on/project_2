"""Authorization precedes search/count/sort/TXT; forbidden values never enter DTOs."""
from datetime import date,datetime,UTC,timedelta
import json,re
from app.services import access
from app.repositories import audit_repository as Repo
from app.utils.date_utils import format_calendar_date,format_system_timestamp

LABELS={'id':'ID аудиту','at':'Час (UTC)','actor_user_id':'ID автора','actor':'Логін автора','object_type':'Об’єкт','object_id':'ID об’єкта','person_id':'person_id','operation':'Операція','before':'Було','after':'Стало','reason':'Причина / результат'}
FORBIDDEN=re.compile(r'password|secret|token|csrf|challenge|ciphertext|digest|credential|public_key|sign_count|fingerprint|storage_key|^import_key$|^identity_key$',re.I)

def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items() if not FORBIDDEN.search(str(k))}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,(date,datetime)):return value.isoformat()
    return value

def changed(row):
    before=row['before'];after=row['after']
    return [(key,before.get(key),after.get(key)) for key in sorted(before.keys()|after.keys()) if before.get(key)!=after.get(key)]

def field_label(key):
    from app.services.backups.emergency_catalog import LABELS as DOMAIN
    return {**DOMAIN,'username':'Логін','display_name':'Ім’я користувача','role':'Системна роль','actor_user_id':'ID автора','user_id':'ID користувача'}.get(key,key)

def display(value):
    if isinstance(value,str):
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):return format_calendar_date(value)
        if re.match(r'^\d{4}-\d{2}-\d{2}T',value):
            try:return format_system_timestamp(datetime.fromisoformat(value))
            except ValueError:pass
    return value

def normalized(source,row,lookup):
    actor=getattr(row,'actor_user_id',getattr(row,'actor_id',None));pid=getattr(row,'person_id',None)
    object_type=source;object_id=getattr(row,'object_id',None)
    if object_id is None:object_id=row.id
    category=getattr(row,'category',None)
    if source=='account':object_type='user';object_id=row.user_id
    if source=='access':object_type='access';object_id=row.target_user_id
    if source=='document':category='documents';object_id=row.document_id;object_type='document'
    if source=='personnel':
        category='family' if row.entity=='family' else 'personal' if row.entity in ('education','directives') else 'medical'
        object_type=row.entity;object_id=row.entity_id
    if source=='assignment':category='service';object_id=row.assignment_id;pid=lookup['assignments'].get(object_id)
    if source=='event':category='events';object_id=row.event_id;pid=lookup['events'].get(object_id)
    if source=='organization':category='organization';object_id=row.org_unit_id
    if source=='subject':object_type=row.object_type
    before=getattr(row,'before',None);after=getattr(row,'after',None)
    changes=getattr(row,'changes',None)
    if changes is not None:
        if isinstance(changes,dict) and all(isinstance(v,dict) and set(v)<={'old','new'} for v in changes.values()):
            before={k:v.get('old') for k,v in changes.items()};after={k:v.get('new') for k,v in changes.items()}
        else:
            before=changes.get('before',{}) if isinstance(changes,dict) else {}
            after=changes.get('after',changes) if isinstance(changes,dict) else changes
    if source in ('account','access'):
        linked=(after or {}).get('person_id') or (before or {}).get('person_id')
        if isinstance(linked,int) and not isinstance(linked,bool):pid=linked
    return {'id':source+':'+str(row.id),'at':row.occurred_at.replace(tzinfo=UTC).isoformat(),
        'actor_user_id':actor,'actor':lookup['actors'].get(actor,'Автор невідомий' if source!='account' else 'Неідентифікований'),
        'object_type':object_type,'object_id':object_id,'person_id':pid,'operation':row.operation,
        'before':clean(before or {}),'after':clean(after or {}),'reason':getattr(row,'reason',None) or '',
        '_category':category,'_medical':source=='document' and object_id in lookup['medical_documents']}

def visible(e,row):
    if e.user.role=='admin':return True
    category=row['_category'];pid=row['person_id']
    if category=='organization':
        if row['object_type']=='positions':
            return all(e.allowed('organization',position_id=row['object_id'],unit_id=s.get('org_unit_id')) and e.allowed('history',position_id=row['object_id'],unit_id=s.get('org_unit_id')) for s in (row['before'],row['after']) if s)
        units={s.get('org_unit_id') for s in (row['before'],row['after']) if s} if row['object_type'] in ('staff_versions','staff_structures') else {row['object_id']}
        return all(e.allowed('organization',unit_id=unit) and e.allowed('history',unit_id=unit) for unit in units)
    if not pid or not e.allowed('history',person_id=pid) or not e.allowed(category,person_id=pid):return False
    for state in (row['before'],row['after']):
        other=state.get('person_id') if isinstance(state,dict) else None
        if other and (not e.allowed(category,person_id=other) or not e.allowed('history',person_id=other)):return False
    if row['_medical'] and not e.allowed('medical',person_id=pid):return False
    if row['object_type']=='persons' and not e.allowed('documents',person_id=pid):
        for state in (row['before'],row['after']):state.pop('tax_number',None)
    return True

def entries(db,kind,*,user_id=None,backup=None,export_authorized=False):
    if kind not in ('system','subject','backup'):raise ValueError('Невідомий журнал.')
    if not export_authorized:access.system_manager(db,user_id)
    lookup=Repo.lookups(db)
    if kind=='backup':
        if backup is None:
            from app.services.backups.commands import backend
            backup=backend(db)
        for event in backup.store.events():
            actor=event['actor_user_id']
            yield {'id':'backup:'+event['id'],'at':event['at'],'actor_user_id':actor,
                'actor':lookup['actors'].get(actor,'Серверна операція' if actor is None else 'Автор невідомий'),
                'object_type':'backup','object_id':event['backup_id'],'person_id':None,
                'operation':event['operation'],'before':{},'after':clean(event['details']),
                'reason':' · '.join(str(v) for v in (event['result'],event.get('code')) if v)}
        return
    e=access.Access(db,user_id) if kind=='subject' and not export_authorized else None
    for source,raw in Repo.rows(db,kind):
        row=normalized(source,raw,lookup)
        if e and not visible(e,row):continue
        row.pop('_category');row.pop('_medical');yield row

def options(params):
    def parse(key):
        raw=params.get(key,'')
        if not raw:return None
        try:return date.fromisoformat(raw)
        except ValueError:raise ValueError('Некоректна дата фільтра.') from None
    start=parse('from');end=parse('to');month=params.get('month','')
    if month:
        try:first=date.fromisoformat(month+'-01')
        except ValueError:raise ValueError('Некоректний місяць.') from None
        last=(first.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
        start=max(start,first) if start else first;end=min(end,last) if end else last
    sorts=params.get('sort','-at,id').split(',')
    if any(s.lstrip('-') not in {*LABELS,'id'} for s in sorts) or len(sorts)>5:raise ValueError('Некоректне сортування.')
    return start,end,sorts

def filtered(db,kind,params,**kwargs):
    start,end,sorts=options(params);result=[]
    actor=params.get('actor','').strip().casefold();operation=params.get('operation','').strip().casefold();q=params.get('q','').strip().casefold()
    if max(len(actor),len(operation),len(q))>500:raise ValueError('Фільтр надто довгий.')
    for row in entries(db,kind,**kwargs):
        on=datetime.fromisoformat(row['at']).date()
        if start and on<start or end and on>end:continue
        if actor and (row['actor_user_id']!=int(actor) if actor.isdecimal() else actor not in row['actor'].casefold()):continue
        if operation and operation not in row['operation'].casefold():continue
        if q and q not in json.dumps(row,ensure_ascii=False,sort_keys=True).casefold():continue
        result.append(row)
    for field in reversed(sorts):
        key=field.lstrip('-');result.sort(key=lambda r:(r[key] is None,r[key] if isinstance(r[key],(int,float)) else str(r[key] or '').casefold()),reverse=field.startswith('-'))
    return result

def page(db,kind,params,**kwargs):
    result=filtered(db,kind,params,**kwargs)
    try:number=max(1,int(params.get('page',1)));size=int(params.get('size',50))
    except (TypeError,ValueError):raise ValueError('Некоректна сторінка.') from None
    if size not in (25,50,100):raise ValueError('Некоректний розмір сторінки.')
    total=len(result);return {'rows':result[(number-1)*size:number*size],'total':total,'page':number,'size':size,'pages':max(1,(total+size-1)//size)}

def text_export(rows):
    def text(v):return json.dumps(v,ensure_ascii=False,sort_keys=True) if isinstance(v,(dict,list)) else str(v if v is not None else '')
    yield '\ufeff'+'\t'.join(LABELS.values())+'\r\n'
    for row in rows:
        yield '\t'.join(text(row.get(k)).replace('\t',' ').replace('\r',' ').replace('\n',' ⏎ ') for k in LABELS)+'\r\n'

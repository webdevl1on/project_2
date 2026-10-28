"""Document operations: separate presence, contents, copies and effective status."""
from datetime import date
from contextlib import contextmanager
import os
import hashlib
import json
from sqlalchemy.exc import SQLAlchemyError
from app.database.transactions import service_transaction
from app.document_schemas import SCHEMAS, STATUSES, PRESENCE, DRIVING_CATEGORIES, DATE_POLICIES
from app.models import DocumentType, PersonDocumentState, PersonDocument, DocumentDetails, DrivingCategory, DocumentAudit, Passport
from app.repositories.document_repository import DocumentRepository as Repo
from app.services.accounts import authorize
from app.utils.date_utils import validate_date_components, validate_field_date

WRITE_ROLES = ('admin','editor')


@contextmanager
def document_transaction(db):
    try:
        with service_transaction(db,immediate=True):yield db
    except SQLAlchemyError:
        raise ValueError('Конфлікт збереження документа; усю операцію скасовано.') from None


def seed_types(db):
    """Participates in caller-owned fresh-schema/migration transaction."""
    for code, (name, primary, _) in SCHEMAS.items():
        if Repo.type(db, code) is None:
            Repo.add(db, DocumentType(code=code, name=name, is_primary=primary, schema_key=code))
    db.flush()


def _text(value, maximum=500):
    if value is None: return None
    if not isinstance(value, str) or len(value.strip()) > maximum or any(ord(c)<32 for c in value):
        raise ValueError(f'Потрібен текст до {maximum} символів без керівних знаків.')
    return value.strip() or None


def _parts(data, prefix, partial=False):
    policy=DATE_POLICIES['passport.'+prefix] if partial else DATE_POLICIES[prefix]
    parts = validate_field_date(policy,*(data.get(prefix+'_'+p) for p in ('day','month','year')))
    return {prefix+'_'+p:getattr(parts,p) for p in ('day','month','year')}


def _type(db, code):
    row = Repo.type(db, code)
    if row is None or row.schema_key not in SCHEMAS or not row.is_active: raise ValueError('Невідомий або неактивний тип документа. Виконайте міграцію довідника.')
    return row


def _record(db, person_id, key, revision=None):
    record = Repo.document(db, key)
    if record is None or record.person_id != person_id: raise ValueError('Документ цієї особи не знайдено.')
    if revision is not None and str(record.revision) != str(revision): raise ValueError('Документ змінено після відкриття форми.')
    return record


def audit(db, actor_id, record, operation, changes, reason=None, *, person_id=None, type_id=None, file_id=None):
    Repo.add(db, DocumentAudit(person_id=record.person_id if record else person_id,
        document_type_id=record.document_type_id if record else type_id, document_id=record.id if record else None,
        actor_id=actor_id, actor_kind='user', operation=operation, changes=changes, reason=reason, file_id=file_id))


def _json(value):
    if isinstance(value, date): return value.isoformat()
    return value


def contents(db, record, kind):
    if kind.code=='passport':
        p = Repo.passport(db, record.passport_id) if record.passport_id else None
        if not p: return {}
        values = {'subtype':p.passport_type, 'series':p.passport_series, 'number':p.passport_number, 'issued_by':p.passport_issued_by}
        for target, source in [('issued','passport_issued'),('expire','passport_expire')]:
            values.update({target+'_'+part:getattr(p, source+'_'+part) for part in ('day','month','year')})
        return values
    if kind.code=='tax_number':
        # Only current value comes from Person; historic changes are in the immutable audit.
        return {'number':Repo.person(db,record.person_id).tax_number} if record.is_current else Repo.archived_snapshot(db,record.id)
    detail = Repo.details(db,record.id)
    result = {c.name:getattr(detail,c.name) for c in DocumentDetails.__table__.columns if c.name not in ('document_id','created_at','updated_at','revision')} if detail else {}
    result['categories'] = [{c.name:getattr(row,c.name) for c in DrivingCategory.__table__.columns if c.name not in ('document_id','created_at','updated_at','revision')} for row in Repo.categories(db,record.id)]
    return result


def _validated(data, code):
    allowed = {'series','number','issued_by','subtype','expiry_mode','extra','categories'} | {p+'_'+c for p in ('issued','expire') for c in ('day','month','year')}
    if set(data)-allowed: raise ValueError('Невідомі поля реквізитів: '+', '.join(sorted(set(data)-allowed)))
    values = {field:_text(data.get(field),100 if field in ('series','number','subtype') else 500) for field in ('series','number','issued_by','subtype')}
    values.update(_parts(data,'issued',code=='passport')); values.update(_parts(data,'expire',code=='passport'))
    mode = data.get('expiry_mode','date' if any(values['expire_'+p] for p in ('day','month','year')) else 'unknown')
    if mode not in ('unknown','date','unlimited'): raise ValueError('Невідомий режим строку дії.')
    if mode != 'date' and any(values['expire_'+p] is not None for p in ('day','month','year')): raise ValueError('Вказані компоненти закінчення потребують режиму date.')
    values['expiry_mode']=mode
    extra=data.get('extra',{})
    if not isinstance(extra,dict) or set(extra)-{'note'}: raise ValueError('Додаткові реквізити: підтримано лише note.')
    note=_text(extra.get('note'),1000) if extra else None
    values['extra']={'note':note} if note else {}
    issued=validate_date_components(*(values['issued_'+p] for p in ('day','month','year')),max_year=9999).as_date()
    expire=validate_date_components(*(values['expire_'+p] for p in ('day','month','year')),max_year=9999).as_date()
    if issued and expire and expire<issued: raise ValueError('Закінчення дії не може передувати даті видачі.')
    return values


def _write_contents(db, record, kind, data):
    if kind.code=='tax_number':
        if data: raise ValueError('Поточний РНОКПП редагується через Person; копіювання номера заборонено.')
        return
    values=_validated(data,kind.code)
    if kind.code=='passport':
        from app.validators.person_validator import PersonValidator as V
        subtype=values['subtype']
        if subtype is not None: subtype=V.validate_passport_type(subtype)
        if subtype=='id':
            values['series']=V.validate_passport_series_id(values['series']); values['number']=V.validate_passport_number_id(values['number'])
            values['issued_by']=V.validate_issued_by_id(values['issued_by'])
        elif subtype=='book':
            values['series']=V.validate_passport_series_book(values['series']); values['number']=V.validate_passport_number_book(values['number'])
            values['issued_by']=V.validate_issued_by_book(values['issued_by'])
        if data.get('categories') or values['extra']: raise ValueError('Для паспорта не підтримуються додаткові реквізити.')
        p=Repo.passport(db,record.passport_id) if record.passport_id else Repo.add(db,Passport(person_id=record.person_id,is_active=record.is_current))
        p.passport_type=subtype
        for source,target in [('series','passport_series'),('number','passport_number'),('issued_by','passport_issued_by')]: setattr(p,target,values[source])
        for source,target in [('issued','passport_issued'),('expire','passport_expire')]:
            for part in ('day','month','year'): setattr(p,target+'_'+part,values[source+'_'+part])
        db.flush();record.passport_id=p.passport_id
        return
    detail=Repo.details(db,record.id) or Repo.add(db,DocumentDetails(document_id=record.id))
    for field,value in values.items(): setattr(detail,field,value)
    categories=data.get('categories',[])
    if not isinstance(categories,list) or len(categories)>20 or (kind.code!='driving_license' and categories): raise ValueError('Категорії дозволено лише для посвідчення водія (до 20).')
    prepared=[];seen=set()
    for category in categories:
        if not isinstance(category,dict) or set(category)-{'category',*(p+'_'+c for p in ('start','expire') for c in ('day','month','year'))}: raise ValueError('Невідомі реквізити категорії.')
        code=category.get('category')
        if code not in DRIVING_CATEGORIES or code in seen: raise ValueError('Невідома або повторна категорія.')
        seen.add(code);fields={**_parts(category,'start'),**_parts(category,'expire')}
        start=validate_date_components(*(fields['start_'+p] for p in ('day','month','year')),max_year=9999).as_date()
        end=validate_date_components(*(fields['expire_'+p] for p in ('day','month','year')),max_year=9999).as_date()
        if start and end and end<start: raise ValueError('Строк категорії завершується раніше початку.')
        prepared.append(DrivingCategory(document_id=record.id,category=code,**fields))
    for old in Repo.categories(db,record.id): Repo.delete(db,old)
    db.flush()
    for row in prepared: Repo.add(db,row)


def _clear_override(record):
    record.override_status=None;record.override_reason=None;record.override_user_id=None
    record.override_fingerprint=None


def _fingerprint(values):
    return hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=False,default=_json).encode()).hexdigest()


def save(db, actor_id, person_id, code, data, *, key=None, revision=None, replaces_id=None):
    try:
        with document_transaction(db):
            authorize(db,actor_id,WRITE_ROLES)
            if Repo.person(db,person_id) is None: raise ValueError('Особу не знайдено.')
            kind=_type(db,code)
            if key is not None:
                if revision is None: raise ValueError('Потрібна revision документа.')
                record=_record(db,person_id,key,revision)
                if record.document_type_id!=kind.id: raise ValueError('Тип документа не змінюється.')
                if replaces_id is not None: raise ValueError('Редагування та заміна — різні операції.')
                old=contents(db,record,kind)
                old_override=record.override_status
            else:
                old={};old_override=None
                if replaces_id is not None:
                    previous=_record(db,person_id,replaces_id,revision)
                    if revision is None or not previous.is_current or previous.document_type_id!=kind.id: raise ValueError('Заміна потребує поточного документа того самого типу та revision.')
                    _archive(db,actor_id,previous,'replace')
                    db.flush()
                elif any(r.is_current and r.document_type_id==kind.id for r in Repo.records(db,person_id)):
                    raise ValueError('Поточний документ цього типу вже є. Використайте явну заміну.')
                record=Repo.add(db,PersonDocument(person_id=person_id,document_type_id=kind.id,replaces_id=replaces_id))
                db.flush()
            _write_contents(db,record,kind,data)
            _clear_override(record)
            # Header revision also guards changes in separate detail/passport rows.
            from datetime import datetime, UTC
            record.updated_at=datetime.now(UTC)
            db.flush()
            new=contents(db,record,kind)
            changes={field:{'old':_json(old.get(field)),'new':_json(new.get(field))} for field in old.keys()|new.keys() if old.get(field)!=new.get(field)}
            if old_override: changes['override_status']={'old':old_override,'new':None}
            audit(db,actor_id,record,'update' if key is not None else 'create',changes)
            result=record.id
        return result
    except SQLAlchemyError: raise ValueError('Конфлікт збереження документа; усю операцію скасовано.') from None


def set_presence(db, actor_id, person_id, code, presence, *, revision=None):
    if presence not in PRESENCE: raise ValueError('Невідомий стан фізичної наявності.')
    with document_transaction(db):
        authorize(db,actor_id,WRITE_ROLES)
        if Repo.person(db,person_id) is None: raise ValueError('Особу не знайдено.')
        kind=_type(db,code)
        if kind.is_primary and presence=='NEVER_OBTAINED': raise ValueError('Основний документ не можна позначити як неотриманий.')
        row=Repo.state(db,person_id,kind.id)
        if row and (revision is None or str(row.revision)!=str(revision)): raise ValueError('Стан наявності вже змінено; потрібна актуальна revision.')
        old=row.presence if row else 'UNKNOWN'
        row=row or Repo.add(db,PersonDocumentState(person_id=person_id,document_type_id=kind.id))
        row.presence=presence
        audit(db,actor_id,None,'presence',{'presence':{'old':old,'new':presence}},person_id=person_id,type_id=kind.id)


def override(db, actor_id, person_id, key, revision, status, reason):
    if revision is None:raise ValueError('Потрібна revision документа.')
    if status is not None and status not in STATUSES: raise ValueError('Невідомий статус заповненості.')
    reason=_text(reason,1000)
    if not reason: raise ValueError('Вкажіть причину ручного коригування або його скасування.')
    with document_transaction(db):
        authorize(db,actor_id,('admin',))
        record=_record(db,person_id,key,revision)
        old=record.override_status
        record.override_status=status;record.override_reason=reason if status else None;record.override_user_id=actor_id if status else None
        kind=next(t for t in Repo.types(db) if t.id==record.document_type_id)
        record.override_fingerprint=_fingerprint(contents(db,record,kind)) if status else None
        audit(db,actor_id,record,'override',{'override_status':{'old':old,'new':status}},reason)


def _archive(db, actor_id, record, reason):
    kind=next(t for t in Repo.types(db) if t.id==record.document_type_id)
    snapshot=contents(db,record,kind)
    record.is_current=False
    if record.passport_id: Repo.passport(db,record.passport_id).is_active=False
    audit(db,actor_id,record,'archive',{'is_current':{'old':True,'new':False},'snapshot':snapshot},reason)


def archive(db,actor_id,person_id,key,revision):
    if revision is None:raise ValueError('Потрібна revision документа.')
    with document_transaction(db):
        authorize(db,actor_id,WRITE_ROLES);record=_record(db,person_id,key,revision)
        if not record.is_current: raise ValueError('Документ уже архівний.')
        _archive(db,actor_id,record,'manual')


def calculated_status(code, values):
    required=list(SCHEMAS[code][2])
    if code=='passport':
        if (values.get('subtype') or '').casefold()=='book': required.append('series')
        elif (values.get('subtype') or '').casefold()=='id': required.append('expire')
    def filled(field):
        if code=='tax_number' and field=='number':
            value=values.get('number')
            return isinstance(value,str) and len(value)==10 and value.isdecimal()
        if field in ('issued','expire'): return all(values.get(field+'_'+p) is not None for p in ('day','month','year'))
        if field=='subtype' and code=='passport': return (values.get(field) or '').casefold() in ('id','book')
        return bool(values.get(field))
    meaningful=any(v not in (None,'',[],{},'unknown') for k,v in values.items() if k!='expiry_mode')
    return 'NOT_FILLED' if not meaningful else ('FILLED' if all(filled(f) for f in required) else 'PARTIALLY_FILLED')


def expiry(values, *, on=None, days=None):
    days=int(os.environ.get('PROJECT2_DOCUMENT_EXPIRY_DAYS','30')) if days is None else days
    if not isinstance(days,int) or not 0<=days<=3660: raise ValueError('Поріг попередження: 0–3660 днів.')
    parts=[values.get('expire_'+p) for p in ('day','month','year')]
    if not any(v is not None for v in parts): return 'UNLIMITED' if values.get('expiry_mode')=='unlimited' else 'UNKNOWN'
    result=validate_date_components(*parts,max_year=9999).as_date()
    if result is None: return 'INCOMPLETE'
    delta=(result-(on or date.today())).days
    return 'EXPIRED' if delta<0 else ('EXPIRING' if delta<=days else 'VALID')


def list_documents(db,actor_id,person_id,**filters):
    authorize(db,actor_id)
    if Repo.person(db,person_id) is None: raise ValueError('Особу не знайдено.')
    rows=Repo.records(db,person_id); result=[]
    for kind in Repo.types(db):
        state=Repo.state(db,person_id,kind.id);presence=state.presence if state else 'UNKNOWN'
        selected=[r for r in rows if r.document_type_id==kind.id]
        for record in selected or [None]:
            values=contents(db,record,kind) if record else ({'number':Repo.person(db,person_id).tax_number} if kind.code=='tax_number' else {})
            auto=calculated_status(kind.schema_key,values)
            stale=bool(record and record.override_status and record.override_fingerprint!=_fingerprint(values))
            effective=((record.override_status if not stale else None) or auto) if record else auto
            files=Repo.files(db,record.id) if record else []
            item={'id':record.id if record else None,'type':kind.code,'presence':presence,'presence_revision':state.revision if state else None,
                  'automatic_status':auto,'effective_status':effective,
                  'override_status':record.override_status if record else None,'override_stale':stale,
                  'override_reason':record.override_reason if record else None,'has_copies':any(not f.is_removed for f in files),
                  'files':[{'id':f.id,'name':f.original_name,'side':f.side,'removed':f.is_removed} for f in files],
                  'is_current':record.is_current if record else True,'revision':record.revision if record else None,
                  'expiry':expiry(values),'values':values,
                  'category_expiry':{r['category']:expiry(r) for r in values.get('categories',[])},
                  'needs_requisites':presence!='NEVER_OBTAINED' and (record is None or record.is_current) and effective!='FILLED',
                  'needs_copies':presence!='NEVER_OBTAINED' and (record is None or record.is_current) and not any(not f.is_removed for f in files)}
            if all(item.get(k)==v for k,v in filters.items()): result.append(item)
    return result


def audit_entries(db,actor_id,person_id):
    authorize(db,actor_id)
    if Repo.person(db,person_id) is None:raise ValueError('Особу не знайдено.')
    return [{'id':r.id,'actor_id':r.actor_id,'actor_kind':r.actor_kind,
        'occurred_at':r.occurred_at.isoformat()+'Z','document_id':r.document_id,'file_id':r.file_id,
        'operation':r.operation,'changes':r.changes,'reason':r.reason} for r in Repo.audits(db,person_id)]

"""Contact validation and atomic primary/archive operations; no HTTP or SQL."""
import re
from urllib.parse import quote
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from app.database.transactions import service_transaction
from app.repositories.contact_repository import ContactRepository as Repo
from app.services.service_person_checking import ServicePersonCheck

TYPES={'phone':'Телефонні номери','email':'Електронна пошта'}

class ContactError(ValueError):
    def __init__(self,message,field='value'):
        super().__init__(message);self.field=field


def normalized(kind,value):
    if not isinstance(value,str): raise ContactError('Контакт повинен бути текстом.')
    value=value.strip()
    if not value: raise ContactError('Заповніть контактне значення.')
    if len(value)>320: raise ContactError('Контакт надто довгий.')
    if kind=='phone':
        if not re.fullmatch(r'\+?[0-9 ()-]+',value) or value.count('(')!=value.count(')'):
            raise ContactError('Вкажіть номер цифрами, з необов’язковим +, пробілами, дужками або дефісами.')
        digits=re.sub(r'[^0-9]','',value)
        if digits.startswith('00'): digits=digits[2:]
        if not 7<=len(digits)<=15: raise ContactError('Телефон повинен містити від 7 до 15 цифр; код країни не додається автоматично.')
        return value,digits
    if kind!='email': raise ContactError('Невідомий тип контакту.','contact_type')
    if len(value)>254 or not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~.-]+@[^\s@]+",value): raise ContactError('Вкажіть коректну електронну адресу.')
    local,domain=value.rsplit('@',1)
    try:domain=domain.encode('idna').decode('ascii').lower()
    except UnicodeError:raise ContactError('Некоректний домен email.') from None
    if len(local)>64 or local.startswith('.') or local.endswith('.') or '..' in local or '.' not in domain or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',part) for part in domain.split('.')):
        raise ContactError('Вкажіть коректну електронну адресу.')
    return value,local.casefold()+'@'+domain


def mutate(db,person_id,data,key=None):
    try:
        with service_transaction(db,immediate=True):
            ServicePersonCheck.get_person_or_raise(person_id,db)
            record=Repo.get(db,person_id,key) if key else None
            if key and (record is None or str(record.revision)!=str(data.get('revision'))):
                raise ContactError('Контакт уже змінено або недоступний. Оновіть дані перед збереженням.','revision')
            if record and not record.is_active: raise ContactError('Архівний контакт доступний лише для перегляду.','revision')
            action=data.get('action','save')
            if action != 'save' and record is None: raise ContactError('Контакт не знайдено.')
            if action=='archive':
                record.is_primary=False;record.is_active=False
            elif action in ('primary','unprimary'):
                if not record: raise ContactError('Контакт не знайдено.')
                primary=action=='primary'
                if primary:
                    for old in Repo.list(db,person_id):
                        if old.contact_type==record.contact_type and old.is_active and old.is_primary and old.id!=record.id: old.is_primary=False
                    db.flush()
                record.is_primary=primary
            elif action=='save':
                kind=data.get('contact_type')
                if record and kind!=record.contact_type: raise ContactError('Тип контакту змінювати не можна.','contact_type')
                value,normal=normalized(kind,data.get('value',''))
                for old in Repo.list(db,person_id):
                    if old.is_active and old.contact_type==kind and old.normalized_value==normal and (record is None or old.id!=record.id):
                        raise ContactError('Такий активний контакт уже існує в цієї особи.')
                label=(data.get('label') or '').strip();note=(data.get('note') or '').strip()
                if len(label)>100:raise ContactError('Підпис: максимум 100 символів.','label')
                if len(note)>1000:raise ContactError('Примітка: максимум 1000 символів.','note')
                primary=data.get('is_primary') in ('on','true','1',True)
                if primary:
                    for old in Repo.list(db,person_id):
                        if old.is_active and old.contact_type==kind and old.is_primary:old.is_primary=False
                    db.flush()
                record=record or Repo.add(db,person_id,kind)
                record.value=value;record.normalized_value=normal;record.label=label or None;record.note=note or None;record.is_primary=primary
            else:raise ContactError('Невідома дія.')
    except IntegrityError:
        raise ContactError('Конфлікт контактів: перевірте дублікати й основний контакт.') from None
    except SQLAlchemyError:
        raise ContactError('Не вдалося зберегти контакт. Оновіть дані та повторіть спробу.','revision') from None


def page(db,person_id):
    ServicePersonCheck.get_person_or_raise(person_id,db)
    records=Repo.list(db,person_id)
    return {'person_id':person_id,'contact_types':TYPES,
        'contact_groups':{kind:[r for r in records if r.is_active and r.contact_type==kind] for kind in TYPES},
        'contact_archive':[r for r in records if not r.is_active], 'mailto':lambda value:'mailto:'+quote(value,safe='@')}


def summary(context):
    result={}
    for kind,records in context['contact_groups'].items():
        primary=next((r for r in records if r.is_primary),None)
        result[kind]={'record':primary or next(iter(records),None),'primary':primary is not None,'additional':len(records)-(1 if primary else 0)}
    return result

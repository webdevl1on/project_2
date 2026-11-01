"""Trusted field policies, never executable definitions from client/SQL data."""
from app.date_fields import DateField, DATE_FIELDS

DATE_POLICIES = {
    'passport.issued': DATE_FIELDS['passport.passport_issued_date'],
    'passport.expire': DATE_FIELDS['passport.passport_expire_date'],
    **{prefix:DateField(prefix,label) for prefix,label in [('issued','Дата видачі'),('expire','Закінчення дії'),('start','Початок категорії')]},
}
SCHEMAS = {
    'passport': ('Паспорт громадянина України', True, ('subtype','number','issued','issued_by')),
    'tax_number': ('РНОКПП', True, ('number',)),
    'military': ('Військово-обліковий документ', True, ('subtype','number','issued')),
    'birth_certificate': ('Свідоцтво про народження', True, ('series','number','issued','issued_by')),
    'driving_license': ('Посвідчення водія', False, ('series','number','issued','categories')),
    'combatant': ('Посвідчення УБД', False, ('series','number','issued','issued_by')),
    'marriage_certificate': ('Свідоцтво про шлюб', False, ('series','number','issued','issued_by')),
    'other': ('Інший документ', False, ('number',)),
}
STATUSES = ('NOT_FILLED','PARTIALLY_FILLED','FILLED')
PRESENCE = ('PRESENT','NEVER_OBTAINED','UNKNOWN')
CORE_CODES = {code for code, spec in SCHEMAS.items() if spec[1]}
DRIVING_CATEGORIES = {'A1','A','B1','B','C1','C','D1','D','BE','C1E','CE','D1E','DE','T'}

# Trusted presentation metadata for the existing document editor, not SQL definitions.
PRESENCE_LABELS = {'PRESENT':'Наявний','NEVER_OBTAINED':'Не отримували','UNKNOWN':'Невідомо'}
STATUS_LABELS = {'NOT_FILLED':'Не заповнено','PARTIALLY_FILLED':'Частково заповнено','FILLED':'Заповнено'}
EXPIRY_LABELS = {'UNKNOWN':'Строк не зазначено','INCOMPLETE':'Дата строку неповна','UNLIMITED':'Безстроковий','VALID':'Строк чинний','EXPIRING':'Строк скоро завершується','EXPIRED':'Строк завершився'}
FILE_SIDE_LABELS = {'front':'Лицьова сторона','back':'Зворотна сторона','page':'Додаткова сторінка','other':'Інша копія'}


def editor_schema(key):
    """Serializable UI contract backed by existing validation/storage policies."""
    if key not in SCHEMAS:return None
    if key=='tax_number':
        return {'fields':[{'key':'number','label':'РНОКПП','kind':'readonly','max_length':10}], 'required_for_filled':list(SCHEMAS[key][2]),'categories':False}
    fields=[]
    if key=='passport':
        fields.append({'key':'subtype','label':'Тип паспорта','kind':'select','choices':{'book':'Книжечка','id':'ID-картка'}})
    elif key in ('military','other'):
        fields.append({'key':'subtype','label':'Вид документа','kind':'text','max_length':100})
    for name,label,maximum in [('series','Серія',100),('number','Номер',100)]:
        fields.append({'key':name,'label':label,'kind':'text','max_length':maximum})
    for name,label in [('issued','Дата видачі'),('expire','Строк дії до')]:
        if name=='expire' and key!='passport':
            fields.append({'key':'expiry_mode','label':'Строк дії','kind':'select','choices':{'unknown':'Невідомо','date':'До зазначеної дати','unlimited':'Безстроковий'}})
        policy=DATE_POLICIES['passport.'+name] if key=='passport' else DATE_POLICIES[name]
        fields.append({'key':name,'label':label,'kind':'partial_date' if key=='passport' else 'date','policy':policy.metadata()})
    fields.append({'key':'issued_by','label':'Орган видачі','kind':'text','max_length':500})
    if key!='passport':fields.append({'key':'note','label':'Додаткові відомості','kind':'text','max_length':1000})
    return {'fields':fields,'required_for_filled':list(SCHEMAS[key][2]),'categories':key=='driving_license'}

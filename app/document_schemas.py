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

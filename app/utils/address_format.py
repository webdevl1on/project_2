"""Pure postal formatting: never rewrites stored text or needs a database."""
import re
from app.geography import SETTLEMENT_TYPES, STREET_TYPES, SETTLEMENT_TYPE_ALIASES, normalize

UA_REGIONS = {'вінницька','волинська','дніпропетровська','донецька','житомирська','закарпатська','запорізька','івано-франківська','київська','кіровоградська','луганська','львівська','миколаївська','одеська','полтавська','рівненська','сумська','тернопільська','харківська','херсонська','хмельницька','черкаська','чернівецька','чернігівська'}
UA_COUNTRIES = {'україна','украина','ukraine','ua','ukr'}
SPECIAL_REGIONS = {'київ','севастополь','ар крим','арк','автономна республіка крим','крим'}


def abbreviated_type(value, types):
    key=normalize(value)
    if types is SETTLEMENT_TYPES:
        key=SETTLEMENT_TYPE_ALIASES.get(key,key)
    if key == 'смт.' and types is SETTLEMENT_TYPES: return 'смт'
    if key in types: return types[key]
    for abbreviation in types.values():
        if key==normalize(abbreviation): return abbreviation
    return value


def typed_name(kind, name, types):
    if not name: return kind and abbreviated_type(kind,types) or ''
    # Existing full words/abbreviations win over a redundant separate type.
    prefixes=set(types) | set(types.values())
    if types is SETTLEMENT_TYPES:
        prefixes.add('смт.')
    for prefix in sorted(prefixes,key=len,reverse=True):
        boundary=r'(?=\s|[^\W\d_]|$)' if prefix.endswith('.') else r'(?=\s|$)'
        match=re.match(r'^'+re.escape(prefix)+boundary,name,re.IGNORECASE)
        if match:
            abbreviation=abbreviated_type(prefix,types)
            rest=name[match.end():].strip()
            # Repeated spellings already present in legacy text are display-only deduplicated.
            while True:
                boundary=r'(?=\s|[^\W\d_]|$)' if abbreviation.endswith('.') else r'(?=\s|$)'
                repeated=re.match(r'^'+re.escape(abbreviation)+boundary,rest,re.IGNORECASE)
                if not repeated: break
                rest=rest[repeated.end():].strip()
            return ' '.join(filter(None,[abbreviation,rest]))
    if kind and (normalize(name)==normalize(kind) or normalize(name).startswith(normalize(kind)+' ')):
        return name
    return ' '.join(filter(None,[abbreviated_type(kind,types),name]))


def administrative(value, full_word, abbreviation):
    if not value: return ''
    base=re.sub(r'(?:\s+(?:'+full_word+'|'+re.escape(abbreviation)+r'))+$','',value,flags=re.IGNORECASE).strip()
    return f'{base} {abbreviation}' if base else abbreviation


def format_address(record, *, extended=False):
    def value(key):
        raw=record.get(key) if isinstance(record,dict) else getattr(record,key,None)
        return str(raw).strip() if raw is not None else ''
    country=value('country'); region=value('region'); district=value('district')
    region_base=re.sub(r'\s+(область|обл\.)$','',normalize(region))
    special=re.sub(r'^м\.\s*','',normalize(region))
    ukrainian=normalize(country) in UA_COUNTRIES or (not country and (region_base in UA_REGIONS or special in SPECIAL_REGIONS))
    if ukrainian:
        if special not in SPECIAL_REGIONS and (region_base in UA_REGIONS or re.search(r'\s+(область|обл\.)$',region,re.IGNORECASE)):
            region=administrative(region,'область','обл.')
        elif special in {'київ','севастополь'} and re.sub(r'^м\.\s*','',normalize(value('settlement'))) == special:
            region=''
        district=administrative(district,'район','р-н')
    community=value('community') if extended or not value('settlement') else ''
    parts=[country,region,district,community,
           typed_name(value('settlement_type'),value('settlement'),SETTLEMENT_TYPES),
           typed_name(value('street_type'),value('street'),STREET_TYPES)]
    for key,label in [('house','буд.'),('corps','корп.'),('building','будівля'),('apartment','кв.'),('room','кімн.')]:
        if value(key):parts.append(f'{label} {value(key)}')
    parts.extend([value('postal_code'),value('note')])
    return ', '.join(filter(None,parts))

"""Finite, display-only journal facets; never constructs arbitrary SQL."""
import json
import re

STATIC = {'jf_name':'name','jf_unit':'unit','jf_position_number':'position_number','jf_position_short':'position_short'}


def value(person, key, periods):
    if key in STATIC: return json.dumps(person[STATIC[key]], ensure_ascii=False, separators=(',',':'))
    period = key.removeprefix('jf_')
    index = next((i for i,p in enumerate(periods) if f"date:{p['start']}:{p['end']}" == period), None)
    return person['cells'][index]['filter_value'] if index is not None else None


def label(person, key, periods):
    if key in STATIC: return str(person[STATIC[key]]) if person[STATIC[key]] not in (None,'') else '(Порожньо)'
    index = next(i for i,p in enumerate(periods) if f"date:{p['start']}:{p['end']}" == key.removeprefix('jf_'))
    cell = person['cells'][index]
    if cell.get('filter_label'):return cell['filter_label']
    return cell.get('event_type_name',cell['name'])+(' · '+cell['subtype'] if cell.get('subtype') else '')+(' · Міраж' if cell.get('mirage') else '')


def apply_filters(people, raw, periods):
    keys = [*STATIC, *(f"jf_date:{p['start']}:{p['end']}" for p in periods)]
    active = {}
    for key in keys:
        values = raw.getlist(key) if hasattr(raw,'getlist') else raw.get(key, [])
        if isinstance(values,str): values=[values]
        if any(not isinstance(v,str) or len(v)>2000 for v in values): raise ValueError('Неприпустиме значення фільтра колонки.')
        if values: active[key]=list(dict.fromkeys(values))
    order = list(dict.fromkeys([*(raw.get('filter_order') or '').split(','), *active]))
    order = [key for key in order if key in active]
    result, facets = people, {}
    def choices(rows,key):
        options = {value(p,key,periods):label(p,key,periods) for p in rows}
        return [{'value':v,'label':text} for v,text in sorted(options.items(),key=lambda item:(item[1].casefold(),item[0]))]
    for key in order:
        facets[key]=choices(result,key)
        result=[p for p in result if value(p,key,periods) in active[key]]
    for key in keys:
        if key not in facets: facets[key]=choices(result,key)
    return result, facets, active, order


def columns(periods):
    from app.table_fields import FIELDS
    names = {'name':FIELDS['full_name'].label,'unit':FIELDS['unit_short'].label,
             'position_number':FIELDS['position_number'].label,'position_short':FIELDS['name_short'].label}
    result=[{'key':'row_number','label':'№','system':True}]
    result += [{'key':key,'label':label,'sort':key,'filter_key':'jf_'+key} for key,label in names.items()]
    result += [{'key':f"date:{p['start']}:{p['end']}",'label':p['period'],'sort':f"date:{p['start']}:{p['end']}",
                'filter_key':f"jf_date:{p['start']}:{p['end']}",'bucket':p} for p in periods]
    return result

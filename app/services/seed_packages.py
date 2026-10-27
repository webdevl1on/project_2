"""Read-only package preflight, including trusted manifests and file hashes."""
import csv
import hashlib
import json
from pathlib import Path
from uuid import UUID
from app.services.name_dictionary_import import read_workbook
from app.name_cases import SHEETS, EXCEL_LABELS

TABLES = ('countries','regions','districts','communities','settlements','city_districts','streets','aliases')
KINDS = dict(zip(TABLES[:5], ('country','region','district','community','settlement'))) | {'streets':'street'}
PARENT_COLUMNS = {'regions':('country_id',), 'districts':('region_id',), 'communities':('district_id','region_id'),
    'settlements':('community_id','district_id','region_id'), 'city_districts':('settlement_id',), 'streets':('settlement_id',)}
FK_TABLES = {'country_id':'countries','region_id':'regions','district_id':'districts','community_id':'communities','settlement_id':'settlements'}
HEADERS = {
 'countries':'id;name_uk;iso_alpha2;iso_alpha3;iso_numeric;source_id;source_row',
 'regions':'id;name;region_type;katottg_code;country_id;country_code;source_id;source_row',
 'districts':'id;name;katottg_code;region_id;source_id;source_row',
 'communities':'id;name;katottg_code;region_id;district_id;source_id;source_row',
 'settlements':'id;name;settlement_type;source_category;katottg_code;region_id;district_id;community_id;source_id;source_row',
 'city_districts':'id;name;katottg_code;region_id;settlement_id;source_id;source_row',
 'streets':'id;name;street_type;settlement_id;external_code;link_method;source_id;source_row;source_region;source_district;source_settlement;source_city_district;full_name',
 'aliases':'id;entity_type;entity_id;alias;alias_kind;first_observed;last_observed;current_observed;valid_from;valid_to;source_id;source_row',
}


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def check_hashes(directory):
    directory=Path(directory).resolve(); manifest=directory/'SHA256SUMS.txt'
    if not manifest.is_file(): raise ValueError(f'{manifest}: немає контрольних сум.')
    verified={}
    for line in manifest.read_text(encoding='utf-8-sig').splitlines():
        digest, relative=line.split(maxsplit=1); relative=relative.lstrip('*')
        path=(directory/relative).resolve()
        if not path.is_relative_to(directory) or len(digest)!=64 or not path.is_file():
            raise ValueError(f'{manifest}: некоректний запис контрольної суми.')
        if sha256(path)!=digest:
            # Git declares CSV eol=lf; published package checksums use CRLF.
            normalized=hashlib.sha256(); normalized_lf=hashlib.sha256()
            if path.suffix.lower() != '.csv': raise ValueError(f'{path.name}: контрольна сума не збігається.')
            class Sink:
                def write(self, value):
                    encoded=value.encode('utf-8')
                    normalized.update(encoded); normalized_lf.update(encoded.replace(b'\r\n',b'\n'))
                    return len(value)
            normalized.update(b'\xef\xbb\xbf'); normalized_lf.update(b'\xef\xbb\xbf')
            with path.open(encoding='utf-8-sig', newline='') as stream:
                writer=csv.writer(Sink(), delimiter=';', lineterminator='\r\n')
                for row in csv.reader(stream, delimiter=';'):
                    writer.writerow(row)
            if normalized.hexdigest()!=digest or normalized_lf.hexdigest()!=sha256(path): raise ValueError(f'{path.name}: контрольна сума не збігається (також після перевірки Git LF/CRLF).')
        verified[relative]=digest
    return verified


def json_file(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def csv_rows(directory, table):
    paths=sorted(Path(directory).glob('streets_[0-9][0-9].csv')) if table=='streets' else [Path(directory)/(table+'.csv')]
    if not paths: raise ValueError('Відсутні streets_*.csv.')
    for path in paths:
        with path.open(encoding='utf-8-sig', newline='') as stream:
            reader=csv.DictReader(stream, delimiter=';')
            if reader.fieldnames!=HEADERS[table].split(';'): raise ValueError(f'{path.name}, рядок 1: неправильні заголовки.')
            for number, row in enumerate(reader,2):
                if not any(row.values()): continue
                if None in row or any(v is None for v in row.values()): raise ValueError(f'{path.name}, рядок {number}: неправильна кількість колонок.')
                yield path.name, number, row


def preflight_geography(directory):
    hashes=check_hashes(directory); sources=json_file(Path(directory)/'sources.json')
    sources={s['id']:s for s in sources}
    validation=json_file(Path(directory)/'validation.json'); files=json_file(Path(directory)/'file_validation.json')
    if validation['status']!='passed' or files['status']!='passed': raise ValueError('Географічний пакет не має успішної перевірки.')
    for source in sources.values():
        if sha256(Path(directory)/'sources'/source['local_file'])!=source['sha256']:
            raise ValueError('Контрольна сума первинного джерела не збігається.')
    ids={}; counts={}; ancestry={}; official={}
    for table in TABLES:
        found=set(); codes=set(); count=0
        for filename,number,row in csv_rows(directory,table):
            prefix=f'{filename}, рядок {number}: '
            try:
                UUID(row['id'])
                if row['id'] in found: raise ValueError('повтор зовнішнього UUID.')
                found.add(row['id']); count+=1
                if row['source_id'] not in sources: raise ValueError('невідоме джерело.')
                if table=='aliases':
                    target=row['entity_type']; target=target if target in ids else target+'s'
                    if target not in ids or row['entity_id'] not in ids[target]: raise ValueError('невідомий об’єкт alias.')
                    continue
                required={'countries':('iso_alpha2',),'regions':('country_id','country_code','katottg_code'),'districts':('region_id','katottg_code'),'communities':('region_id','katottg_code'),'settlements':('region_id','katottg_code'),'city_districts':('region_id','settlement_id','katottg_code'),'streets':('settlement_id',)}
                if any(not row.get(key) for key in required.get(table,())): raise ValueError('відсутні обов’язкові зовнішні ключі або коди.')
                name=row.get('name_uk',row.get('name',''))
                if not name or len(name)>250: raise ValueError('назва відсутня або надто довга.')
                code=row.get('katottg_code') or row.get('iso_alpha2')
                if code:
                    if code in codes: raise ValueError('повтор офіційного коду в одній категорії.')
                    codes.add(code)
                for column,parent_table in FK_TABLES.items():
                    value=row.get(column)
                    if value and value not in ids.get(parent_table,set()): raise ValueError(f'{column}: невідомий зовнішній ключ.')
                if table in PARENT_COLUMNS:
                    candidates=PARENT_COLUMNS[table]
                    if not any(row.get(key) for key in candidates): raise ValueError('відсутній батьківський об’єкт.')
                    for key in candidates:
                        if row.get(key):
                            for level,value in ancestry.get(row[key],{}).items():
                                if row.get(level) and row[level]!=value: raise ValueError('суперечність географічної ієрархії.')
                if table not in ('streets','city_districts'):
                    ancestry[row['id']]={key:row[key] for key in FK_TABLES if row.get(key)}
                    ancestry[row['id']][{'countries':'country_id','regions':'region_id','districts':'district_id','communities':'community_id','settlements':'settlement_id'}[table]]=row['id']
            except (ValueError,KeyError) as error: raise ValueError(prefix+str(error)) from None
        ids[table]=found; counts[table]=count
        if validation['counts'].get(table)!=count: raise ValueError(f'{table}: кількість {count} не відповідає validation.json.')
    for item in files['excel_native_checks']:
        # Excel/CSV equivalence is reported by the package; verify aggregate counts independently.
        if item['table'] in counts and item['table']!='settlements' and item['rows']!=counts[item['table']]:
            raise ValueError('file_validation.json: розбіжність кількості записів.')
    return {'counts':counts,'sources':sources,'hashes':hashes,'excluded':{'unresolved_streets':validation.get('unresolved_streets',0),'hierarchy_gaps':validation.get('hierarchy_gaps',0),'excluded_countries':len(validation.get('excluded_country_records',[]))},'digest':sha256(Path(directory)/'SHA256SUMS.txt')}


def preflight_names(directory):
    hashes=check_hashes(directory); manifest=json_file(Path(directory)/'manifest.json'); validation=json_file(Path(directory)/'validation.json')
    if validation['status']!='passed': raise ValueError('Словниковий пакет не пройшов перевірку.')
    seen=set(); total=0; books=[]
    for item in manifest:
        path=Path(directory)/item['file']
        if path.name!=item['file'] or not path.name.startswith('project_2_dictionary_') or path.name not in hashes:
            raise ValueError('manifest.json: неприпустимий файл словника.')
        from openpyxl import load_workbook
        book=load_workbook(path,read_only=True,data_only=False)
        try:
            for sheet in SHEETS:
                if sheet not in book.sheetnames or tuple(cell.value for cell in next(book[sheet].iter_rows(min_row=2,max_row=2),()))!=EXCEL_LABELS:
                    raise ValueError(f'{path.name}, {sheet}, рядок 2: потрібні українські підписи.')
        finally: book.close()
        rows,errors=read_workbook(path.read_bytes())
        if errors: raise ValueError(f'{path.name}: '+'; '.join(errors))
        counts={sheet:0 for sheet in SHEETS}
        for row in rows:
            v=row['values']; key=(v['kind'],v['sex'],v['normalized_key'])
            if key in seen: raise ValueError(f'{path.name}, {row["sheet"]}, рядок {row["row"]}: дубль між книгами.')
            seen.add(key); counts[row['sheet']]+=1
        if len(rows)!=item['records'] or counts!=item['sheets']: raise ValueError(f'{path.name}: кількість не відповідає manifest.json.')
        total+=len(rows); books.append(path)
    if total!=validation['records']: raise ValueError('Кількість словників не відповідає validation.json.')
    return {'count':total,'books':books,'hashes':hashes,'digest':sha256(Path(directory)/'SHA256SUMS.txt')}

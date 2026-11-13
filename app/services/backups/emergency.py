"""One-way readable emergency archive. No restore/import or HTTP file delivery."""
from contextlib import nullcontext
from datetime import datetime,date,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import json,os,tempfile,time,uuid,re,shutil,hashlib
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from sqlalchemy import select,text
from sqlalchemy.orm import Session
from app.database.base import Base
from app.database.postgresql import REVISION,require_postgresql_schema
from app.repositories.backup_repository import BackupRepository as Repo
from app.services import access,audit
from app.models import User
from app.utils.date_utils import format_partial_date,format_calendar_date,format_system_timestamp
from .crypto import private_dir,private_file,sha,canonical,METADATA_LIMIT
from .safe_files import SafeTree,safe_name,no_links,parts
from .windows_storage import local_root
from .bundle import inventory,validate_refs
from .emergency_catalog import TABLES,EVENT_TABLES,OMIT,LABELS
from .store import now,stamp,key

BOOKS=('Персональні_дані.xlsx','Події_та_служба.xlsx','Аудит.xlsx')
ROW_LIMIT=1048576
CELL_LIMIT=32000

def authorize_export(db,user_id):
    """Protected system operation from the agreed Master/Admin backup policy.

This authorizes only worker publication to guarded configured storage, never
subject DTOs, HTTP file download, arbitrary paths or ordinary subject reads.
The HTTP command requires fresh MFA; automation requires a scoped Master permit.
"""
    return access.system_manager(db,user_id)

def approve(backup,actor,reason,days,confirmed):
    if confirmed is not True or not isinstance(reason,str) or not reason.strip() or len(reason)>2000 or type(days) is not int or not 0<=days<=30:raise ValueError('EMERGENCY_APPROVAL_REQUIRED')
    with Session(backup.db_engine) as db:
        user=authorize_export(db,actor)
        if user.role!='master':raise PermissionError('EMERGENCY_MASTER_APPROVAL_REQUIRED')
    permit={'actor_user_id':actor,'expires_at':(now()+timedelta(days=days)).isoformat() if days else None,'active':True,'reason':reason.strip(),'environment':backup.initialize()}
    backup.ring.save(backup.config.root/'emergency-permit.json',permit)
    backup.store.event('emergency_approval','SUCCESS',actor=actor,details={'expires_at':permit['expires_at']})

def authorize_scheduled(backup):
    try:permit=backup.ring.read(backup.config.root/'emergency-permit.json')
    except ValueError:raise ValueError('EMERGENCY_APPROVAL_REQUIRED') from None
    if not permit.get('active') or permit['expires_at'] and datetime.fromisoformat(permit['expires_at'])<=now() or permit['environment']!=backup.initialize():raise ValueError('EMERGENCY_APPROVAL_EXPIRED')
    with Session(backup.db_engine) as db:
        user=authorize_export(db,permit['actor_user_id'])
        if user.role!='master':raise PermissionError('EMERGENCY_MASTER_APPROVAL_REQUIRED')

def formatted(value):
    if isinstance(value,datetime):return format_system_timestamp(value)
    if isinstance(value,date):return format_calendar_date(value)
    if isinstance(value,(dict,list)):
        def dates(v):
            if isinstance(v,dict):return {k:dates(item) for k,item in v.items()}
            if isinstance(v,list):return [dates(item) for item in v]
            return audit.display(v)
        return json.dumps(dates(audit.clean(value)),ensure_ascii=False,sort_keys=True)
    return value

class Sheets:
    """Streaming worksheets, split at Excel limits; long cells use numbered parts."""
    def __init__(self,book,name,columns):
        self.book=book;self.name=name;self.columns=columns;self.count=0;self.part=0;self.sheet=None;self.start()
    def start(self):
        if self.sheet is not None:self.sheet.auto_filter.ref=f'A1:{column_letter(len(self.columns)+2)}{self.count}'
        self.part+=1;name=self.name[:25]+(f' {self.part}' if self.part>1 else '')
        self.sheet=self.book.create_sheet(name);self.sheet.freeze_panes='C2';self.count=1
        self.append_raw([label for _,label in self.columns]+['Частина тексту','Усього частин'])
    def append_raw(self,values):
        cells=[]
        for v in values:
            cell=WriteOnlyCell(self.sheet,value=v)
            # Force text even when it begins with =,+,-,@. Excel never executes it.
            if isinstance(v,str):cell.data_type='s'
            cells.append(cell)
        self.sheet.append(cells)
    def add(self,row):
        values=[formatted(row.get(k)) for k,_ in self.columns]
        chunks=max([1,*[(len(v)+CELL_LIMIT-1)//CELL_LIMIT for v in values if isinstance(v,str)]])
        for part in range(chunks):
            if self.count>=ROW_LIMIT:self.start()
            self.append_raw([v[part*CELL_LIMIT:(part+1)*CELL_LIMIT] if isinstance(v,str) and len(v)>CELL_LIMIT else v for v in values]+[part+1,chunks]);self.count+=1
    def finish(self):self.sheet.auto_filter.ref=f'A1:{column_letter(len(self.columns)+2)}{self.count}'

def column_letter(number):
    from openpyxl.utils import get_column_letter
    return get_column_letter(number)

class ExportData:
    def __init__(self,db):
        self.db=db;self.people={};self.links={};self.names={}
        for row in db.execute(select(Base.metadata.tables['persons'])).mappings():self.people[row['person_id']]=dict(row)
        names=list(db.execute(select(Base.metadata.tables['person_names'])).mappings())
        grouped={}
        for name in names:grouped.setdefault(name['person_id'],[]).append(name)
        for pid in self.people:
            rows=grouped.get(pid,[]);active=[n for n in rows if n['is_active']]
            chosen=rows[0] if len(rows)==1 else active[0] if len(active)==1 else None
            if len(active)>1:raise ValueError('EMERGENCY_PERSON_NAME_AMBIGUOUS')
            self.names[pid]=dict(chosen) if chosen else {}
            self.people[pid]['person_full_name']=' '.join(chosen.get(k,'') or '' for k in ('surname','name','patronymic')).strip() if chosen else 'ПІБ не зазначено'
        # Small stable ID maps avoid N+1 queries for indirect personal records.
        for table,pk in [('person_names','person_name_id'),('person_documents','id')]:
            t=Base.metadata.tables[table];self.links[table]=dict(db.execute(select(t.c[pk],t.c.person_id)).all())
        t=Base.metadata.tables['person_assignments'];self.links['person_assignments']=dict(db.execute(select(t.c.id,t.c.person_id)).all())
    def person(self,table,row):
        if 'person_id' in row:return row['person_id']
        if table=='person_name_cases':return self.links['person_names'].get(row['person_name_id'])
        if 'document_id' in row:return self.links['person_documents'].get(row['document_id'])
        if table=='org_reassignments':return self.links['person_assignments'].get(row['assignment_id'])
        return None
    def rows(self,table):
        t=Base.metadata.tables[table]
        for row in self.db.execute(select(t).order_by(*t.primary_key).execution_options(yield_per=500)).mappings():
            row=dict(row);pid=self.person(table,row)
            if pid is not None:
                row['person_id']=pid;row['person_full_name']=self.people[pid]['person_full_name']
            yield row

def columns(table):
    names=[c.name for c in Base.metadata.tables[table].columns if c.name not in OMIT]
    result=[]
    if table in ('person_name_cases','document_details','document_driving_categories','document_files','medical_document_links','org_reassignments') or 'person_id' in names:
        result=[('person_id','person_id'),('person_full_name','Повне ПІБ')];names=[n for n in names if n!='person_id']
    for name in names:
        if name.endswith(('_day','_month','_year')):
            prefix=name.rsplit('_',1)[0]
            if name.endswith('_day'):
                target=prefix+'_date'
                if target not in [k for k,_ in result]:result.append((target,LABELS[target]))
            continue
        if name not in [k for k,_ in result]:result.append((name,LABELS[name]))
    if table=='persons':result.append(('archive_paths',LABELS['archive_paths']))
    return result

def partials(row):
    for name in list(row):
        if name.endswith('_day'):
            prefix=name[:-4];values=[row.get(prefix+'_'+p) for p in ('day','month','year')]
            row[prefix+'_date']=format_partial_date(*values) if any(v is not None for v in values) else ''
    return row

def file_archive(backup,data,payload):
    root=backup.config.emergency_root;tree=SafeTree(root);manifest_path=backup.config.root/'emergency-files.json'
    manifest=backup.ring.read(manifest_path) if manifest_path.exists() else {'files':[]}
    known={(r['source_id'],r['sha256']):r for r in manifest['files']};folders={};counts={}
    for old in manifest['files']:
        tree.check(old['path'],old['sha256'])
        if old['person_id'] is not None:folders.setdefault(old['person_id'],set()).add(str(Path(old['path']).parent))
        group=(old['person_id'],old['type']);counts[group]=max(counts.get(group,0),old['number'])
    types={r['id']:r for r in data.rows('document_types')}
    documents={r['id']:r for r in data.rows('person_documents')}
    subtypes={r['document_id']:r['subtype'] for r in data.rows('document_details')}
    occupied={r['path'].casefold() for r in manifest['files']}
    births={pid:(format_partial_date(p['birth_day'],p['birth_month'],p['birth_year']) if any(p[k] is not None for k in ('birth_day','birth_month','birth_year')) else 'дата народження невідома') for pid,p in data.people.items()}
    bases={pid:safe_name(p['person_full_name'],90)+' — '+births[pid] for pid,p in data.people.items()}
    from collections import Counter
    duplicates=Counter(v.casefold() for v in bases.values())
    for pid in bases:
        if duplicates[bases[pid].casefold()]>1:bases[pid]+=' (person_id '+str(pid)+')'
    used=sum(p.stat().st_size for p in root.rglob('*') if p.is_file())
    def add(source_id,pid,kind,title,source,digest,extension):
        nonlocal used
        if (source_id,digest) in known:return
        no_links(source)
        if not source.is_file() or sha(source)!=digest:raise ValueError('EMERGENCY_SOURCE_FILE_MISSING_OR_CHANGED')
        if used+source.stat().st_size>backup.config.emergency_max_bytes:raise ValueError('EMERGENCY_QUOTA_EXCEEDED')
        if shutil.disk_usage(root).free<source.stat().st_size+1024**2:raise ValueError('STORAGE_INSUFFICIENT_SPACE')
        group=(pid,kind);number=counts.get(group,0)+1
        person=data.names.get(pid,{})
        initials=' '.join([person.get('surname',''),*[person.get(k,'')[:1] for k in ('name','patronymic') if person.get(k)] ]).strip()
        folder=bases.get(pid,'Нерозподілені фото')
        filename=safe_name(title+' '+initials,95)+' '+str(number)+extension
        path='Документи/'+folder+'/'+filename
        if path.casefold() in occupied:
            tag=hashlib.sha256(source_id.encode('utf-8')).hexdigest()[:12]
            filename=safe_name(title+' '+initials,95)+' '+str(number)+' (джерело '+tag+')'+extension
            path='Документи/'+folder+'/'+filename
        if tree.copy(source,path,digest):used+=source.stat().st_size
        item={'source_id':source_id,'person_id':pid,'type':kind,'number':number,'path':path,'sha256':digest,'size':source.stat().st_size,'at':stamp()}
        manifest['files'].append(item);backup.ring.save(manifest_path,manifest);known[(source_id,digest)]=item;counts[group]=number
        occupied.add(path.casefold())
        if pid is not None:folders.setdefault(pid,set()).add(str(Path(path).parent))
    for row in data.rows('document_files'):
        document=documents[row['document_id']];typ=document['document_type_id']
        subtype=(subtypes.get(row['document_id']) or '').strip() if types[typ]['code'] in ('military','other') else ''
        title=subtype or types[typ]['name'];kind='document:'+str(typ)+(':'+subtype.casefold() if subtype else '')
        ext=Path(row['original_name']).suffix.lower()
        if not re.fullmatch(r'\.[A-Za-z0-9]{1,12}',ext):raise ValueError('EMERGENCY_FILE_EXTENSION_INVALID')
        # storage keys are only used privately to locate the immutable source.
        storage=row['storage_key']
        add('document_file:'+str(row['id']),row['person_id'],kind,title,payload/'documents'/storage,row['sha256'],ext)
    photo_entries=[]
    if backup.config.photo_index:
        source_index=payload/'photo-index.json';no_links(source_index)
        try:photo_entries=json.loads(source_index.read_text(encoding='utf-8'))
        except (OSError,ValueError):raise ValueError('EMERGENCY_PHOTO_INDEX_INVALID') from None
        if not isinstance(photo_entries,list):raise ValueError('EMERGENCY_PHOTO_INDEX_INVALID')
    indexed=set();source_ids=set()
    for item in photo_entries:
        if not isinstance(item,dict) or item.get('person_id') not in data.people or not isinstance(item.get('source_id'),str) or item['source_id'] in source_ids:raise ValueError('EMERGENCY_PHOTO_INDEX_INVALID')
        relative='/'.join(parts(item['relative_path']));source=payload/'photos'/relative;no_links(source)
        if relative in indexed or not source.is_file():raise ValueError('EMERGENCY_PHOTO_INDEX_INVALID')
        source_ids.add(item['source_id']);indexed.add(relative)
        add('photo:'+item['source_id'],item['person_id'],'portrait','Фото обличчя',source,sha(source),source.suffix.lower())
    for source in sorted((payload/'photos').rglob('*')):
        if source.is_file():
            relative=source.relative_to(payload/'photos').as_posix()
            if relative not in indexed:add('unmapped_photo:'+relative,None,'unmapped','Нерозподілене фото',source,sha(source),source.suffix.lower())
    return manifest,{pid:'\n'.join(sorted(v)) for pid,v in folders.items()}

def write_books(backup,db,target,payload):
    data=ExportData(db);files,folders=file_archive(backup,data,payload)
    books=[Workbook(write_only=True) for _ in BOOKS]
    sheets=[];counts={}
    try:
        for table,title in TABLES.items():
            sheet=Sheets(books[1 if table in EVENT_TABLES else 0],title,columns(table));sheets.append(sheet);counts[table]=0
            for row in data.rows(table):
                if table=='persons':row['person_full_name']=data.people[row['person_id']]['person_full_name'];row['archive_paths']=folders.get(row['person_id'],'')
                sheet.add(partials(row));counts[table]+=1
        for kind,title in [('system','Системний аудит'),('subject','Аудит даних'),('backup','Аудит резервування')]:
            columns_=[(k,v) for k,v in audit.LABELS.items()];columns_.insert(6,('person_full_name','Повне ПІБ'))
            sheet=Sheets(books[2],title,columns_);sheets.append(sheet)
            for row in audit.entries(db,kind,backup=backup,export_authorized=True):
                if row['person_id'] is not None:row['person_full_name']=data.people.get(row['person_id'],{}).get('person_full_name','ПІБ не збережено в джерелі')
                row['at']=format_system_timestamp(datetime.fromisoformat(row['at']));sheet.add(row)
        for sheet in sheets:sheet.finish()
        for book,name in zip(books,BOOKS):book.save(target/name)
    finally:
        for book in books:book.close()
    return files,counts

def generate(backup,*,actor=None,job_id=None):
    if backup._worker_lock is None:
        with backup.operation_lock():return generate(backup,actor=actor,job_id=job_id)
    if not backup.config.emergency_root:raise ValueError('EMERGENCY_ROOT_REQUIRED')
    backup.check_storage()
    if actor is None:authorize_scheduled(backup)
    else:
        with Session(backup.db_engine) as db:authorize_export(db,actor)
    private_dir(backup.config.emergency_root)
    local_root(backup,backup.config.emergency_root);local_root(backup,backup.config.staging)
    start=time.monotonic();identity=job_id or uuid.uuid4().hex;key(identity)
    existing=backup.config.root/'emergency'/(identity+'.json')
    if existing.exists():
        result=load_manifest(backup,backup.ring.read(existing));verify(backup,result)
        return {'id':result['id'],'day':result['day'],'files':len(result['files']),'size':sum(v['size'] for v in result['books'].values())}
    backup.store.event('emergency','RUNNING',actor=actor)
    try:
        require_postgresql_schema(backup.db_engine)
        with tempfile.TemporaryDirectory(prefix='emergency-',dir=backup.config.staging) as raw:
            stage=Path(raw);payload=stage/'payload';private_dir(payload);excel=stage/'Excel';private_dir(excel)
            with backup.db_engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection,connection.begin():
                with Repo.freeze(backup._worker_lock):
                    connection.execute(text('SELECT pg_export_snapshot()'))
                    inventory(backup.settings.paths['documents'],payload/'documents',immutable=True);inventory(backup.settings.paths['photos'],payload/'photos')
                    if backup.config.photo_index:
                        no_links(backup.config.photo_index)
                        with backup.config.photo_index.open('rb') as inp,private_file(payload/'photo-index.json') as out:shutil.copyfileobj(inp,out)
                validate_refs(payload,Repo.references(connection))
                with Session(bind=connection) as db:files,counts=write_books(backup,db,excel,payload)
            version=now().astimezone(ZoneInfo('Europe/Kyiv')).strftime('%Y-%m-%d_%H%M%S')+'_'+identity
            relative='Excel/'+version;tree=SafeTree(backup.config.emergency_root)
            manifest={'id':identity,'at':stamp(),'day':now().astimezone(ZoneInfo('Europe/Kyiv')).date().isoformat(),'revision':REVISION,'release':backup.config.release,'path':relative,'books':{},'files':files['files'],'counts':counts,'ready':True}
            size=sum(p.stat().st_size for p in backup.config.emergency_root.rglob('*') if p.is_file())
            if size+sum((excel/name).stat().st_size for name in BOOKS)>backup.config.emergency_max_bytes:raise ValueError('EMERGENCY_QUOTA_EXCEEDED')
            for name in BOOKS:
                checksum=sha(excel/name);tree.copy(excel/name,relative+'/'+name,checksum);manifest['books'][name]={'sha256':checksum,'size':(excel/name).stat().st_size}
            # Ready marker is published last; an incomplete directory is never offered.
            encoded=canonical(manifest)
            if len(encoded)>METADATA_LIMIT:raise ValueError('EMERGENCY_MANIFEST_TOO_LARGE')
            with private_file(stage/'manifest.json') as out:out.write(encoded)
            tree.copy(stage/'manifest.json',relative+'/manifest.json',sha(stage/'manifest.json'))
            private_dir(backup.config.root/'emergency')
            # The signed index is small; status/latest never loads every historical
            # version's full cumulative file catalogue into web-process memory.
            header={k:v for k,v in manifest.items() if k!='files'}
            header.update(file_count=len(manifest['files']),manifest_sha256=sha(stage/'manifest.json'))
            backup.ring.save(existing,header)
        verify(backup,manifest)
        result={'id':identity,'day':manifest['day'],'files':len(files['files']),'size':sum(v['size'] for v in manifest['books'].values()),'seconds':time.monotonic()-start}
        backup.store.event('emergency','SUCCESS',actor=actor,details=result);return result
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).startswith(('EMERGENCY_','STORAGE_')) else 'EMERGENCY_GENERATION_FAILED'
        backup.store.event('emergency','FAILED',actor=actor,code=code);raise ValueError(code) from None

def verify(backup,manifest):
    manifest=load_manifest(backup,manifest)
    if not manifest.get('ready') or set(manifest['books'])!=set(BOOKS):raise ValueError('EMERGENCY_NOT_READY')
    tree=SafeTree(backup.config.emergency_root)
    for name,value in manifest['books'].items():tree.check(manifest['path']+'/'+name,value['sha256'])
    for record in manifest['files']:tree.check(record['path'],record['sha256'])

def latest(backup):
    records=backup.store.records('emergency')
    if not records:raise ValueError('EMERGENCY_NOT_READY')
    result=load_manifest(backup,max(records,key=lambda r:r['at']));verify(backup,result);return result

def load_manifest(backup,record):
    if 'files' in record:return record # Existing signed format remains compatible.
    raw=SafeTree(backup.config.emergency_root).read(record['path']+'/manifest.json',METADATA_LIMIT)
    if hashlib.sha256(raw).hexdigest()!=record['manifest_sha256']:raise ValueError('EMERGENCY_MANIFEST_CHANGED')
    try:manifest=json.loads(raw)
    except ValueError:raise ValueError('EMERGENCY_MANIFEST_INVALID') from None
    if manifest.get('id')!=record['id'] or manifest.get('path')!=record['path'] or len(manifest.get('files',[]))!=record['file_count']:raise ValueError('EMERGENCY_MANIFEST_CHANGED')
    return manifest

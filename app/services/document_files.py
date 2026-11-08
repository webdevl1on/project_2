"""File metadata/audit commit together; failed publication is compensated."""
from app.services.access_context import actor_operation
from app.models import DocumentFile
from app.repositories.document_repository import DocumentRepository as Repo
from app.services import access
from app.services.documents import _record, _text, audit, document_transaction
from app.services.document_storage import DocumentStorage


@actor_operation
def attach(db,actor_id,person_id,key,revision,content,filename,side,*,storage=None,request_id=None):
    if revision is None:raise ValueError('Потрібна revision документа.')
    access.require_document(db,person_id,key,'edit',actor_id)
    if side not in ('front','back','page','other'): raise ValueError('Невідома сторона/сторінка документа.')
    # A basename is display metadata only, never a storage path.
    filename=_text((filename or '').replace('\\','/').split('/')[-1],250) or 'document'
    if request_id is not None and (not isinstance(request_id,str) or not 16<=len(request_id)<=100):raise ValueError('Некоректний ідентифікатор завантаження.')
    storage=storage or DocumentStorage();prepared=storage.prepare(content)
    try:
        with document_transaction(db):
            access.require(db,'documents','edit',person_id=person_id,actor_id=actor_id);record=_record(db,person_id,key)
            receipt=Repo.upload_receipt(db,key,request_id) if request_id else None
            if receipt:
                previous=Repo.file(db,receipt.file_id)
                if previous.sha256!=prepared['sha256'] or previous.original_name!=filename:raise ValueError('Ідентифікатор вже використано для іншої копії.')
                storage.discard(prepared)
                return previous.id
            record=_record(db,person_id,key,revision)
            row=Repo.add(db,DocumentFile(document_id=record.id,storage_key=prepared['key'],original_name=filename,
                content_type=prepared['mime'],size=prepared['size'],sha256=prepared['sha256'],side=side,sort_order=max((f.sort_order for f in Repo.files(db,key)),default=0)+1))
            db.flush()
            audit(db,actor_id,record,'file_add',{'file':{'old':None,'new':{'id':row.id,'name':filename,'side':side,'sha256':row.sha256,'sort_order':row.sort_order}},'request_id':request_id},file_id=row.id)
            from datetime import datetime, UTC
            record.updated_at=datetime.now(UTC)
            storage.publish(prepared)
            result=row.id
        return result
    except Exception:
        storage.discard(prepared);raise


@actor_operation
def remove(db,actor_id,person_id,file_id,revision,reason):
    reason=_text(reason,1000)
    if not reason: raise ValueError('Вкажіть причину вилучення копії.')
    with document_transaction(db):
        access.require(db,'documents','edit',person_id=person_id,actor_id=actor_id);row=Repo.file(db,file_id)
        if not row: raise ValueError('Копію не знайдено.')
        record=_record(db,person_id,row.document_id)
        if str(row.revision)!=str(revision) or row.is_removed: raise ValueError('Копію вже змінено або вилучено.')
        row.is_removed=True
        audit(db,actor_id,record,'file_remove',{'is_removed':{'old':False,'new':True}},reason,file_id=row.id)


@actor_operation
def download(db,actor_id,person_id,file_id,*,history=False,storage=None):
    access.require(db,'documents',person_id=person_id,actor_id=actor_id)
    if history:access.require(db,'history',person_id=person_id,actor_id=actor_id)
    row=Repo.file(db,file_id)
    if row is None or (row.is_removed and not history): raise ValueError('Копію не знайдено.')
    access.require_document(db,person_id,row.document_id,actor_id=actor_id)
    _record(db,person_id,row.document_id)
    path=(storage or DocumentStorage()).path(row.storage_key)
    if not path.is_file(): raise ValueError('Файл сховища недоступний; метадані та журнал збережені.')
    return row,path


@actor_operation
def reorder(db,actor_id,person_id,key,ids,revision):
    with document_transaction(db):
        access.require(db,'documents','edit',person_id=person_id,actor_id=actor_id)
        if revision is None:raise ValueError('Потрібна revision документа.')
        record=_record(db,person_id,key,revision)
        rows=Repo.files(db,key);active=[f for f in rows if not f.is_removed]
        if not isinstance(ids,list) or any(type(i) is not int for i in ids) or len(ids)!=len(set(ids)) or set(ids)!={f.id for f in active}:raise ValueError('Передайте всі активні копії цього документа без повторів.')
        before=[f.id for f in active];by_id={f.id:f for f in active}
        for index,file_id in enumerate(ids,1):by_id[file_id].sort_order=index
        from datetime import datetime, UTC
        record.updated_at=datetime.now(UTC)
        audit(db,actor_id,record,'file_order',{'order':{'old':before,'new':ids}})

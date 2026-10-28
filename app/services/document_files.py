"""File metadata/audit commit together; failed publication is compensated."""
from app.models import DocumentFile
from app.repositories.document_repository import DocumentRepository as Repo
from app.services.accounts import authorize
from app.services.documents import WRITE_ROLES, _record, _text, audit, document_transaction
from app.services.document_storage import DocumentStorage


def attach(db,actor_id,person_id,key,revision,content,filename,side,*,storage=None):
    if revision is None:raise ValueError('Потрібна revision документа.')
    authorize(db,actor_id,WRITE_ROLES)
    if side not in ('front','back','page','other'): raise ValueError('Невідома сторона/сторінка документа.')
    # A basename is display metadata only, never a storage path.
    filename=_text((filename or '').replace('\\','/').split('/')[-1],250) or 'document'
    storage=storage or DocumentStorage();prepared=storage.prepare(content)
    try:
        with document_transaction(db):
            authorize(db,actor_id,WRITE_ROLES);record=_record(db,person_id,key,revision)
            row=Repo.add(db,DocumentFile(document_id=record.id,storage_key=prepared['key'],original_name=filename,
                content_type=prepared['mime'],size=prepared['size'],sha256=prepared['sha256'],side=side))
            db.flush()
            audit(db,actor_id,record,'file_add',{'file':{'old':None,'new':{'id':row.id,'name':filename,'side':side,'sha256':row.sha256}}},file_id=row.id)
            storage.publish(prepared)
            result=row.id
        return result
    except Exception:
        storage.discard(prepared);raise


def remove(db,actor_id,person_id,file_id,revision,reason):
    reason=_text(reason,1000)
    if not reason: raise ValueError('Вкажіть причину вилучення копії.')
    with document_transaction(db):
        authorize(db,actor_id,WRITE_ROLES);row=Repo.file(db,file_id)
        if not row: raise ValueError('Копію не знайдено.')
        record=_record(db,person_id,row.document_id)
        if str(row.revision)!=str(revision) or row.is_removed: raise ValueError('Копію вже змінено або вилучено.')
        row.is_removed=True
        audit(db,actor_id,record,'file_remove',{'is_removed':{'old':False,'new':True}},reason,file_id=row.id)


def download(db,actor_id,person_id,file_id,*,history=False,storage=None):
    authorize(db,actor_id,('admin',) if history else ('admin','editor','viewer'))
    row=Repo.file(db,file_id)
    if row is None or (row.is_removed and not history): raise ValueError('Копію не знайдено.')
    _record(db,person_id,row.document_id)
    path=(storage or DocumentStorage()).path(row.storage_key)
    if not path.is_file(): raise ValueError('Файл сховища недоступний; метадані та журнал збережені.')
    return row,path

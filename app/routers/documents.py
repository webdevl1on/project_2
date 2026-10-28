"""Protected infrastructure API; the full document editor is a subsequent stage."""
from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.security.accounts import current_user
from app.services import documents as service, document_files
from app.services.document_storage import MAX_FILE_SIZE

router=APIRouter(prefix='/persons/{person_id}/documents',tags=['Documents'])


def failure(error):
    return JSONResponse({'detail':str(error)},status_code=403 if isinstance(error,PermissionError) else 409,
                        headers={'Cache-Control':'no-store'})


async def payload(request):
    try: data=await request.json()
    except ValueError: raise HTTPException(400,'Неправильний JSON.') from None
    if not isinstance(data,dict): raise HTTPException(400,'Потрібен об’єкт JSON.')
    return data


@router.get('/audit')
def audit_log(person_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        return JSONResponse({'entries':service.audit_entries(db,user.id,person_id)},headers={'Cache-Control':'no-store'})
    except (PermissionError,ValueError) as error:return failure(error)


@router.get('')
def listing(person_id:int,code:str|None=None,status:str|None=None,presence:str|None=None,copies:bool|None=None,
            current:bool|None=None,expiry:str|None=None,automatic_status:str|None=None,needs_requisites:bool|None=None,
            needs_copies:bool|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    filters={key:value for key,value in [('type',code),('effective_status',status),('automatic_status',automatic_status),('presence',presence),
        ('has_copies',copies),('is_current',current),('expiry',expiry),('needs_requisites',needs_requisites),('needs_copies',needs_copies)] if value is not None}
    try: return JSONResponse({'documents':service.list_documents(db,user.id,person_id,**filters)},headers={'Cache-Control':'no-store'})
    except (ValueError,PermissionError) as error:return failure(error)


@router.post('')
@router.post('/{key:int}')
async def save(request:Request,person_id:int,key:int|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    data=await payload(request)
    try:
        if not isinstance(data.get('details',{}),dict):raise ValueError('details має бути об’єктом.')
        key=service.save(db,user.id,person_id,data.get('type'),data.get('details',{}),key=key,revision=data.get('revision'),replaces_id=data.get('replaces_id'))
        return {'ok':True,'id':key}
    except (ValueError,PermissionError) as error:return failure(error)


@router.post('/presence')
async def presence(request:Request,person_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    data=await payload(request)
    try:
        service.set_presence(db,user.id,person_id,data.get('type'),data.get('presence'),revision=data.get('revision'))
        return {'ok':True}
    except (ValueError,PermissionError) as error:return failure(error)


@router.post('/{key:int}/override')
async def override(request:Request,person_id:int,key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    data=await payload(request)
    try:
        if data.get('revision') is None: raise ValueError('Потрібна revision.')
        service.override(db,user.id,person_id,key,data['revision'],data.get('status'),data.get('reason'));return {'ok':True}
    except (ValueError,PermissionError) as error:return failure(error)


@router.post('/{key:int}/archive')
async def archive(request:Request,person_id:int,key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    data=await payload(request)
    try:
        if data.get('revision') is None:raise ValueError('Потрібна revision.')
        service.archive(db,user.id,person_id,key,data['revision']);return {'ok':True}
    except (ValueError,PermissionError) as error:return failure(error)


@router.post('/{key:int}/files')
async def upload(person_id:int,key:int,file:UploadFile=File(),revision:int=Form(),side:str=Form('other'),user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        file_id=document_files.attach(db,user.id,person_id,key,revision,await file.read(MAX_FILE_SIZE+1),file.filename,side)
        return {'ok':True,'id':file_id}
    except (ValueError,PermissionError,OSError) as error:return failure(error)
    finally:await file.close()


@router.get('/files/{file_id:int}')
def download(person_id:int,file_id:int,history:bool=False,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        row,path=document_files.download(db,user.id,person_id,file_id,history=history)
        return FileResponse(path,media_type=row.content_type,filename=row.original_name,
            headers={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; sandbox"})
    except (ValueError,PermissionError) as error:return failure(error)


@router.post('/files/{file_id:int}/remove')
async def remove(request:Request,person_id:int,file_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    data=await payload(request)
    try:
        document_files.remove(db,user.id,person_id,file_id,data.get('revision'),data.get('reason'));return {'ok':True}
    except (ValueError,PermissionError) as error:return failure(error)

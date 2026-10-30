"""HTTP adapter for protected personnel processes; business rules live in service."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.security.accounts import current_user
from app.routers.documents import payload, failure
from app.services import medical

router=APIRouter(prefix='/persons/{person_id}/medical',tags=['Medical and awards'])

@router.get('')
def listing(person_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    try:return JSONResponse(medical.page(db,user.id,person_id),headers={'Cache-Control':'no-store'})
    except (ValueError,PermissionError) as error:return failure(error)

@router.post('/active')
async def active(request:Request,person_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    data=await payload(request)
    try:
        key=data.get('exam_id')
        if key is not None and type(key) is not int:raise ValueError('Потрібен ID ВЛК або null.')
        medical.select_active(db,user.id,person_id,key,data.get('revision'));return {'ok':True}
    except (ValueError,PermissionError) as error:return failure(error)

@router.post('/{kind}/{key:int}/documents')
async def link(request:Request,person_id:int,kind:str,key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    data=await payload(request)
    try:return {'ok':True,'document_id':medical.link_document(db,user.id,person_id,kind,key,data.get('category'),document_id=data.get('document_id'),revision=data.get('revision'))}
    except (ValueError,PermissionError) as error:return failure(error)

@router.post('/{kind}')
@router.post('/{kind}/{key:int}')
async def save(request:Request,person_id:int,kind:str,key:int|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    data=await payload(request)
    try:return {'ok':True,**medical.save(db,user.id,person_id,kind,data.get('fields'),key=key,revision=data.get('revision'))}
    except (ValueError,PermissionError) as error:return failure(error)

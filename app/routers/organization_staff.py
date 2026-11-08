"""Administrative HTTP boundary; imports/mapping never infer organizational IDs."""
from io import BytesIO
from datetime import date
from fastapi import APIRouter,Request,Depends,HTTPException,UploadFile,File,Form
from fastapi.responses import Response,JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database.db import get_db
from app.security.accounts import current_user
from app.security.admin import session_owner
from app.services import organization_staff as service,organization_import as importing,dictionary_previews
from app.services.organization_excel import empty_template
from app.services.staff_service import domain_date,today
from app.templating import templates

router=APIRouter(prefix='/admin/organization/staff')


def failure(error):
    if isinstance(error,PermissionError):return JSONResponse({'detail':str(error)},403)
    if isinstance(error,(ValueError,KeyError,TypeError)):return JSONResponse({'detail':str(error) if isinstance(error,ValueError) else 'Перевірте поля запиту.'},409)
    return JSONResponse({'detail':'Операцію відхилено через конфлікт або помилку збереження. Змін немає.'},409)

async def data(request):
    body=await request.json()
    if not isinstance(body,dict):raise ValueError('Потрібні поля об’єкта JSON.')
    return body

@router.get('')
def page(request:Request,unit_id:int,on:date|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    try:context=service.page_data(db,user.id,unit_id,on or today())
    except (ValueError,PermissionError) as error:raise HTTPException(400,str(error)) from None
    if 'application/json' in request.headers.get('accept',''):return context
    return templates.TemplateResponse(request=request,name='admin/organization_staff.html',context={'staffing':context})

@router.get('/template')
def template(request:Request,depth:int=3,user=Depends(current_user),db:Session=Depends(get_db)):
    from app.services.organization import authorize
    authorize(db,user.id,'view')
    try:content=empty_template(depth)
    except ValueError as error:raise HTTPException(422,str(error)) from None
    return Response(content,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="organization_positions.xlsx"'})

@router.post('/map-structure')
@router.post('/map-positions')
async def mapping(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        body=await data(request)
        if request.url.path.endswith('/map-structure'):service.bind_structure(db,user.id,int(body['structure_id']),int(body['unit_id']),int(body['revision']))
        else:service.bind_positions(db,user.id,int(body['version_id']),body['mappings'])
        return {'ok':True}
    except (ValueError,PermissionError,KeyError,TypeError,SQLAlchemyError) as error:return failure(error)

@router.post('/preview')
async def preview(request:Request,file:UploadFile=File(...),scope_id:int=Form(...),mode:str=Form(...),on:date=Form(...),end:date|None=Form(None),name:str=Form(''),version_id:int|None=Form(None),user=Depends(current_user),db:Session=Depends(get_db)):
    owner=session_owner(request)
    try:
        if not file.filename or not file.filename.lower().endswith('.xlsx'):raise ValueError('Виберіть файл .xlsx.')
        raw=await file.read(5*1024*1024+1)
        if len(raw)>5*1024*1024:raise ValueError('Excel перевищує 5 МБ.')
        prepared=importing.preview(db,user.id,BytesIO(raw),scope_id,mode,on,end,name,version_id)
        token=dictionary_previews.store(prepared,owner,resource='organization-staff')
        return {'prepared':importing.preview_data(db,user.id,prepared),'token':token}
    except (ValueError,PermissionError,KeyError,TypeError) as error:return failure(error)
    finally:await file.close()

@router.post('/confirm')
async def confirm(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        body=await data(request);prepared,_=dictionary_previews.load(body['token'],session_owner(request),resource='organization-staff')
        key=importing.confirm(db,user.id,prepared,body.get('selected_rows',[]),reason=body.get('reason'),replace_ids=body.get('replace_ids',[]),confirm_removal=body.get('confirm_removal') is True)
        return {'ok':True,'receipt_id':key,'receipt':importing.receipt_data(db,user.id,key)}
    except (ValueError,PermissionError,KeyError,TypeError,SQLAlchemyError) as error:return failure(error)

@router.get('/imports/{key:int}')
def receipt(key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    try:return importing.receipt_data(db,user.id,key)
    except (ValueError,PermissionError) as error:raise HTTPException(404,str(error)) from None

@router.post('/imports/{key:int}/confirm')
@router.post('/imports/{key:int}/withdraw')
@router.post('/imports/{key:int}/resolve')
async def receipt_action(request:Request,key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        body=await data(request)
        if request.url.path.endswith('/withdraw'):
            if body.get('confirmed') is not True:raise ValueError('Підтвердьте відкликання імпорту.')
            importing.withdrawal(db,user.id,key,body.get('reason'))
        elif request.url.path.endswith('/resolve'):
            importing.resolve_conflict(db,user.id,key,int(body['row_number']),body.get('decision'),body.get('reason'),body.get('revision'))
        else:
            prepared=importing.receipt_for_confirmation(db,user.id,key)
            importing.confirm(db,user.id,prepared,body.get('selected_rows',[]),reason=body.get('reason'),replace_ids=body.get('replace_ids',[]),confirm_removal=body.get('confirm_removal') is True)
        return {'ok':True,'receipt_id':key,'receipt':importing.receipt_data(db,user.id,key)}
    except (ValueError,PermissionError,KeyError,TypeError,SQLAlchemyError) as error:return failure(error)

@router.post('/reassign/{key:int}')
async def reassign(request:Request,key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        body=await data(request)
        if body.get('confirmed') is not True:raise ValueError('Підтвердьте фактичні дати та реквізити призначення.')
        details={**body,'order_date':domain_date(body.get('order_date'),False),'release_date':domain_date(body.get('release_date'),False)}
        assigned=service.resolve_reassignment(db,user.id,key,int(body['revision']),int(body['position_id']),domain_date(body.get('assigned_from')),domain_date(body.get('assigned_to'),False),details)
        return {'ok':True,'assignment_id':assigned}
    except (ValueError,PermissionError,KeyError,TypeError,SQLAlchemyError) as error:return failure(error)


@router.post('/close-coverage')
async def close_coverage(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        body=await data(request)
        if body.get('confirmed') is not True:raise ValueError('Підтвердьте завершення джерела штатки.')
        service.close_coverage(db,user.id,int(body['id']),int(body['revision']),domain_date(body.get('end')))
        return {'ok':True}
    except (ValueError,PermissionError,KeyError,TypeError,SQLAlchemyError) as error:return failure(error)

"""Administrative organization HTTP boundary; dated rules live in OrganizationService."""
from datetime import date
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.models.organization import KINDS
from app.security.accounts import current_user
from app.services.organization import OrganizationService,authorize
from app.services.staff_service import domain_date,today
from app.utils.date_utils import parse_exact_date
from app.templating import templates

router=APIRouter(prefix='/admin/organization',tags=['Organization'])
# Separate actions deliberately share only today's Admin policy. Future ACL can
# replace this one hook without treating sorting as reparenting/position binding.
ACTIONS=frozenset({'view','create','edit','reparent','reorder','operational','dissolve','annul'})


def permission(db,user,action):
    if action not in ACTIONS:raise HTTPException(403,'Невідома дія організаційної структури.')
    try:authorize(db,user.id,action)
    except PermissionError as error:raise HTTPException(403,str(error)) from None


class InputError(ValueError):
    def __init__(self,message,field=None):super().__init__(message);self.field=field


def number(value,field,optional=False):
    if optional and value in (None,''):return None
    if type(value) is bool:raise InputError('Потрібен коректний ID або revision.',field)
    try:return int(value)
    except (ValueError,TypeError):raise InputError('Потрібен коректний ID або revision.',field) from None


def calendar(value,field,optional=False):
    try:return parse_exact_date(value,required=not optional) if isinstance(value,str) and '.' in value else domain_date(value,not optional)
    except ValueError as error:raise InputError(str(error),field) from None


async def payload(request):
    try:
        result=await request.json() if request.headers.get('content-type','').split(';')[0]=='application/json' else dict(await request.form())
    except ValueError:raise InputError('Не вдалося прочитати дані форми.') from None
    if not isinstance(result,dict):raise InputError('Потрібен об’єкт із полями.')
    return result


def failure(error):
    return JSONResponse({'ok':False,'detail':str(error),'field':getattr(error,'field',None)},status_code=422 if isinstance(error,InputError) else 409)


def on_date(raw):return calendar(raw,'on') if raw else today()


@router.get('')
def page(request:Request,on:str|None=None,unit_id:int|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    permission(db,user,'view')
    try:
        selected_on=on_date(on);tree=OrganizationService.tree(db,selected_on)
    except ValueError as error:raise HTTPException(422,str(error)) from None
    return templates.TemplateResponse(request=request,name='admin/organization.html',context={'organization_tree':tree,'organization_kinds':KINDS,'selected_unit_id':unit_id})


@router.get('/tree')
def tree(on:str|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    permission(db,user,'view')
    try:return OrganizationService.tree(db,on_date(on))
    except ValueError as error:raise HTTPException(422,str(error)) from None


@router.get('/units/{key:int}')
def detail(key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    permission(db,user,'view')
    try:return OrganizationService.history(db,key)
    except ValueError as error:raise HTTPException(404,str(error)) from None


@router.post('/units')
async def create(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    permission(db,user,'create')
    try:
        data=await payload(request)
        key=OrganizationService.create(db,user.id,data.get('kind'),data.get('name'),calendar(data.get('formed_on'),'formed_on'),
            parent_id=number(data.get('parent_id'),'parent_id',True))
        return {'ok':True,'unit_id':key,'message':'Підрозділ створено. Він може залишатися порожнім.'}
    except PermissionError as error:raise HTTPException(403,str(error)) from None
    except ValueError as error:return failure(error)


@router.post('/reorder')
async def reorder(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    permission(db,user,'reorder')
    try:
        data=await payload(request)
        ids=data.get('ids');revisions=data.get('revisions')
        if not isinstance(ids,list) or not isinstance(revisions,dict):raise InputError('Оновіть дерево перед сортуванням.')
        OrganizationService.reorder(db,user.id,calendar(data.get('on'),'on'),number(data.get('parent_id'),'parent_id',True),ids,revisions=revisions)
        return {'ok':True,'message':'Порядок змінено. Підпорядкування залишилося тим самим.'}
    except PermissionError as error:raise HTTPException(403,str(error)) from None
    except ValueError as error:return failure(error)


@router.post('/units/{key:int}/{action}')
async def change(request:Request,key:int,action:str,user=Depends(current_user),db:Session=Depends(get_db)):
    names={'name':'edit','parent':'reparent','operational':'operational','dissolve':'dissolve','annul':'annul'}
    if action not in names:raise HTTPException(404,'Невідома операція.')
    permission(db,user,names[action])
    try:
        data=await payload(request);revision=number(data.get('revision'),'revision')
        if action=='name':
            OrganizationService.revise(db,user.id,key,revision,calendar(data.get('effective_from'),'effective_from'),name=data.get('name'))
            message='Нову назву збережено з указаної дати.'
        elif action=='parent':
            OrganizationService.revise(db,user.id,key,revision,calendar(data.get('effective_from'),'effective_from'),parent_id=number(data.get('parent_id'),'parent_id',True))
            message='Основне підпорядкування збережено з указаної дати.'
        elif action=='operational':
            # Revision applies to the selected child, not to another unit's form.
            OrganizationService.add_operational(db,user.id,key,number(data.get('parent_id'),'parent_id'),calendar(data.get('valid_from'),'valid_from'),calendar(data.get('valid_to'),'valid_to',True),note=data.get('note'),revision=revision)
            message='Оперативне підпорядкування збережено окремо від основного.'
        elif action=='dissolve':
            if data.get('confirmed') is not True:raise InputError('Підтвердьте розформування.','confirmed')
            OrganizationService.dissolve(db,user.id,key,revision,calendar(data.get('dissolved_on'),'dissolved_on'))
            message='Підрозділ розформовано. Його історія та ID збережені.'
        else:
            if data.get('confirmed') is not True:raise InputError('Підтвердьте анулювання.','confirmed')
            OrganizationService.annul(db,user.id,key,revision,data.get('reason'))
            message='Помилковий підрозділ анульовано зі збереженням історії.'
        return {'ok':True,'unit_id':key,'message':message}
    except PermissionError as error:raise HTTPException(403,str(error)) from None
    except ValueError as error:return failure(error)


@router.post('/operational/{key:int}/close')
async def close_operational(request:Request,key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    permission(db,user,'operational')
    try:
        data=await payload(request)
        OrganizationService.close_operational(db,user.id,key,number(data.get('revision'),'revision'),calendar(data.get('valid_to'),'valid_to'))
        return {'ok':True,'message':'Оперативне підпорядкування завершено зі збереженням історії.'}
    except PermissionError as error:raise HTTPException(403,str(error)) from None
    except ValueError as error:return failure(error)

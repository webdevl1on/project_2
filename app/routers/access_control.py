"""ACL HTTP boundary. Actor/session always come from verified personal authentication."""
from fastapi import APIRouter,Request,Depends,HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from fastapi.responses import JSONResponse
from app.database.db import get_db
from app.security.accounts import current_user
from app.services import access_management as service,access
from app.templating import templates
router=APIRouter(tags=['Access control'])

def failure(error):
    return JSONResponse({'detail':str(error) if isinstance(error,(ValueError,PermissionError)) else 'Збереження відхилено; усю операцію скасовано.'},403 if isinstance(error,PermissionError) else 409)

@router.get('/admin/access')
def page(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    try:state=service.overview(db,user.id)
    except PermissionError as error:raise HTTPException(403,str(error)) from None
    return templates.TemplateResponse(request=request,name='admin/access.html',context={'access_state':state})

@router.get('/admin/access/data')
def state(user_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    try:return service.matrix(db,user.id,user_id)
    except (ValueError,PermissionError) as error:return failure(error)

@router.get('/admin/access/overview')
def overview(user=Depends(current_user),db:Session=Depends(get_db)):
    try:return service.overview(db,user.id)
    except (ValueError,PermissionError) as error:return failure(error)

@router.get('/admin/access/explain')
def explanation(user_id:int,category:str,action:str='read',person_id:int|None=None,unit_id:int|None=None,position_id:int|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    try:return service.explain(db,user.id,user_id,category,action,{'person_id':person_id,'unit_id':unit_id,'position_id':position_id})
    except (ValueError,PermissionError) as error:return failure(error)

@router.get('/account/access')
def own_access(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    e=access.Access(db,user.id)
    return {'role':user.role,'categories':list(access.CATEGORIES),'units':[key for key in e.states if any(e.allowed(c,unit_id=key) for c in access.CATEGORIES)]}

@router.post('/admin/access/users/{key:int}/{action}')
async def user_action(request:Request,key:int,action:str,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        b=await request.json();why=b.get('reason');revision=b.get('revision')
        if action=='matrix':service.save_matrix(db,user.id,key,b.get('changes'),revision,why)
        elif action=='rule':service.save_rule(db,user.id,key,b.get('rule'),revision,why)
        elif action=='link':service.link_person(db,user.id,key,b.get('person_id'),revision,why)
        elif action=='template':service.assign_template(db,user.id,key,int(b['template_id']),int(b['unit_id']),b.get('starts_at'),b.get('ends_at'),why)
        elif action=='temporary':service.temporary(db,user.id,key,int(b['position_id']),b.get('rules'),b.get('starts_at'),b.get('ends_at'),why)
        elif action=='delegate':service.delegation(db,user.id,key,int(b['unit_id']),b.get('capabilities'),b.get('starts_at'),b.get('ends_at'),why)
        else:raise ValueError('Невідома операція.')
        return {'ok':True,'matrix':service.matrix(db,user.id,key)}
    except (ValueError,PermissionError,TypeError,KeyError,SQLAlchemyError) as error:return failure(error)

@router.post('/admin/access/templates')
@router.post('/admin/access/templates/{key:int}')
async def change_template(request:Request,key:int|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        b=await request.json();key=service.template(db,user.id,b.get('name'),b.get('rules',[]),b.get('reason'),key=key,revision=b.get('revision'),confirmed=b.get('confirmed') is True,copy_from=b.get('copy_from'),is_active=b.get('is_active',True))
        return {'ok':True,'id':key}
    except (ValueError,PermissionError,TypeError,KeyError,SQLAlchemyError) as error:return failure(error)

@router.post('/admin/access/policies/{key:int}')
async def policy(request:Request,key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        b=await request.json();key=service.policy(db,user.id,key,b.get('rules',[]),b.get('reason'),revision=b.get('revision'),confirmed=b.get('confirmed') is True,is_active=b.get('is_active',True));return {'ok':True,'id':key}
    except (ValueError,PermissionError,TypeError,KeyError,SQLAlchemyError) as error:return failure(error)

@router.post('/admin/access/rules/{key:int}/revoke')
@router.post('/admin/access/reviews/{key:int}/resolve')
@router.post('/admin/access/sources/{kind}/{key:int}')
async def change(request:Request,key:int,kind:str|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        b=await request.json()
        if '/reviews/' in request.url.path:service.resolve_review(db,user.id,key,b['revision'],b.get('reason'))
        elif '/rules/' in request.url.path:service.revoke_rule(db,user.id,key,b['revision'],b.get('reason'))
        else:service.change_source(db,user.id,kind,key,b['revision'],b.get('active') is True,b.get('reason'))
        return {'ok':True}
    except (ValueError,PermissionError,TypeError,KeyError,SQLAlchemyError) as error:return failure(error)

@router.get('/admin/access/templates/{key:int}')
def template_data(key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    try:return service.template_data(db,user.id,key)
    except (ValueError,PermissionError) as error:return failure(error)

@router.get('/admin/access/proposal')
def proposal(position_id:int,user=Depends(current_user),db:Session=Depends(get_db)):
    try:return service.proposal(db,user.id,position_id)
    except (ValueError,PermissionError) as error:return failure(error)

"""Personal account management through the existing identity services."""
from fastapi import APIRouter,Request,Depends,HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database.db import get_db
from app.security.accounts import current_user,COOKIE
from app.services import accounts,account_management as view
from app.account_policy import ASSIGNABLE_ROLES,has_role
from app.templating import templates

router=APIRouter()


def render(request,name,**context):
    return templates.TemplateResponse(request=request,name=name,context={'roles':ASSIGNABLE_ROLES if request.state.authenticated_user.role=='master' else {'user':'User'},**context})


@router.get('/admin/users')
def users(request:Request,q:str='',user=Depends(current_user),db:Session=Depends(get_db)):
    try:context=view.listing(db,user.id,q)
    except PermissionError as error:raise HTTPException(403,str(error)) from error
    if 'application/json' in request.headers.get('accept',''):return context
    return render(request,'admin/users.html',**context)


@router.get('/admin/users/new')
def new_user(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    try:accounts.authorize(db,user.id,('master','admin'))
    except PermissionError as error:raise HTTPException(403,str(error)) from error
    return render(request,'admin/user_new.html')


@router.get('/admin/users/audit')
def audit(request:Request,user_id:int|None=None,page:int=1,user=Depends(current_user),db:Session=Depends(get_db)):
    try:context=view.audit_page(db,user.id,user_id,page)
    except PermissionError as error:raise HTTPException(403,str(error)) from error
    if 'application/json' in request.headers.get('accept',''):return context
    return render(request,'admin/account_audit.html',**context)


@router.get('/admin/users/{key:int}')
def account(request:Request,key:int,user=Depends(current_user),db:Session=Depends(get_db)):
    try:context=view.detail(db,user.id,key)
    except ValueError as error:raise HTTPException(404,str(error)) from error
    except PermissionError as error:raise HTTPException(403,str(error)) from error
    if 'application/json' in request.headers.get('accept',''):return context
    return render(request,'admin/user_detail.html',**context)


def revision(data):
    try:return int(data.get('revision'))
    except (ValueError,TypeError):raise ValueError('Некоректна версія запису. Оновіть сторінку.') from None


async def payload(request):
    try:data=await request.json() if request.headers.get('content-type','').split(';')[0]=='application/json' else dict(await request.form())
    except ValueError:raise ValueError('Некоректний запит.') from None
    if not isinstance(data,dict):raise ValueError('Потрібен об’єкт із полями.')
    return data


def confirmed(data):return data.get('confirmed') in (True,'on','1','true')


@router.post('/admin/users/new')
async def create(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        data=await payload(request)
        if data.get('password')!=data.get('confirm_password'):raise ValueError('Підтвердження пароля не збігається.')
        key=accounts.create_user(db,data.get('username'),data.get('display_name'),data.get('password'),data.get('role','user'),actor_id=user.id)
        return {'ok':True,'redirect_to':f'/admin/users/{key}'}
    except PermissionError as error:return JSONResponse({'detail':str(error)},status_code=403)
    except ValueError as error:return JSONResponse({'detail':str(error)},status_code=409)
    except SQLAlchemyError:return JSONResponse({'detail':'Збереження відхилене. Оновіть дані та перевірте унікальність логіна.'},status_code=409)


@router.post('/admin/users/{key:int}')
@router.post('/admin/users/{key:int}/{action}')
async def change(request:Request,key:int,action:str='edit',user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        data=await payload(request);reason=data.get('reason')
        if action=='reset-mfa':
            if data.get('confirmed') is not True:raise ValueError('Підтвердьте перевірку особи.')
            from app.services import mfa
            mfa.recover(db,user.id,key,reason)
            return {'ok':True,'redirect_to':f'/admin/users/{key}'}
        rev=revision(data)
        if action=='edit':accounts.update_user(db,user.id,key,rev,display_name=data.get('display_name'),role=data.get('role'),reason=reason,confirmed=confirmed(data))
        elif action=='state':
            if data.get('active') not in (True,False,'0','1','true','false'):raise ValueError('Вкажіть новий статус користувача.')
            accounts.set_active(db,user.id,key,rev,data.get('active') in (True,'1','true'),confirmed=confirmed(data),reason=reason)
        elif action=='reset-password':accounts.reset_password(db,user.id,key,rev,data.get('password'),data.get('confirm_password'),confirmed=confirmed(data),reason=reason)
        elif action=='revoke-sessions':accounts.revoke_all_sessions(db,user.id,key,rev,confirmed=confirmed(data),reason=reason)
        else:raise ValueError('Невідома операція.')
        revoked=user.id==key and action in ('state','revoke-sessions')
        target='/auth/login' if revoked else '/persons' if not has_role(user,('master','admin')) else f'/admin/users/{key}'
        response=JSONResponse({'ok':True,'redirect_to':target})
        if revoked:response.delete_cookie(COOKIE,path='/')
        return response
    except PermissionError as error:return JSONResponse({'detail':str(error)},status_code=403)
    except ValueError as error:return JSONResponse({'detail':str(error)},status_code=409)
    except SQLAlchemyError:return JSONResponse({'detail':'Збереження відхилене через конфлікт або блокування БД. Оновіть сторінку.'},status_code=409)


@router.get('/account/password')
def own_password(request:Request,user=Depends(current_user)):
    return render(request,'account_password.html')


@router.post('/auth/password')
async def change_own_password(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        data=await payload(request)
        accounts.change_password(db,user.id,data.get('current_password'),data.get('password'),data.get('confirm_password'))
        response=JSONResponse({'ok':True,'redirect_to':'/auth/login'})
        response.delete_cookie(COOKIE,path='/');return response
    except (ValueError,PermissionError) as error:return JSONResponse({'detail':str(error)},status_code=409)
    except SQLAlchemyError:return JSONResponse({'detail':'Пароль не змінено через помилку збереження. Повторіть спробу.'},status_code=409)

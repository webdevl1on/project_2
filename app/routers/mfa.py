"""HTTP boundary for restricted pre-authentication and personal security settings."""
import hmac,base64,io
from fastapi import APIRouter,Request,Depends,HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.security.accounts import current_user,COOKIE,check_origin,secure_transport
from app.services import accounts,mfa
from app.templating import templates

router=APIRouter()
PENDING='project2_pending'

async def pending_request(request,db):
    secure_transport(request);check_origin(request)
    try:user,flow=mfa.pending(db,request.cookies.get(PENDING,''))
    except PermissionError as error:raise HTTPException(401,str(error)) from None
    if request.method!='GET' and not hmac.compare_digest(request.headers.get('x-csrf-token',''),flow.csrf_token):raise HTTPException(403,'Неправильний CSRF-токен етапу MFA.')
    return user,flow

def flow_cookie(request,response,token):
    response.set_cookie(PENDING,token,httponly=True,secure=request.url.scheme=='https',samesite='strict',max_age=300,path='/')
    return response

async def data(request):
    try:value=await request.json()
    except ValueError:raise ValueError('Некоректний JSON.') from None
    if not isinstance(value,dict):raise ValueError('Потрібен об’єкт JSON.')
    return value

@router.get('/auth/mfa')
async def mfa_page(request:Request,db:Session=Depends(get_db)):
    _,flow=await pending_request(request,db)
    return templates.TemplateResponse(request=request,name='mfa.html',context={'embedded_reauth':flow.kind=='reauth' and request.query_params.get('reauth')=='1'})

@router.get('/auth/mfa/state')
async def state(request:Request,db:Session=Depends(get_db)):
    return mfa.state(db,request.cookies.get(PENDING,''))

@router.post('/auth/mfa/{action:path}')
async def pending_action(request:Request,action:str,db:Session=Depends(get_db)):
    await pending_request(request,db);token=request.cookies[PENDING]
    try:
        body=await data(request)
        if action=='totp/start':
            result=mfa.totp_start(db,token)
            import qrcode
            image=qrcode.make(result['uri']);out=io.BytesIO();image.save(out,format='PNG');result['qr']='data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()
        elif action=='totp/confirm':result=mfa.totp_confirm(db,token,body.get('code'))
        elif action=='prove':result=mfa.prove(db,token,body.get('method'),body.get('code'))
        elif action=='passkey/options':result=mfa.passkey_options(db,token,body.get('register') is True)
        elif action=='passkey/verify':result=mfa.passkey_verify(db,token,body.get('credential'),body.get('register') is True,body.get('name','Passkey'))
        elif action=='finish':result=mfa.finish(db,token)
        else:raise HTTPException(404,'Невідома дія.')
        response=JSONResponse({key:value for key,value in result.items() if key!='token'})
        if 'token' in result:
            response.set_cookie(COOKIE,result['token'],httponly=True,secure=request.url.scheme=='https',samesite='strict',max_age=28800,path='/')
        if action=='finish':response.delete_cookie(PENDING,path='/')
        return response
    except PermissionError as error:raise HTTPException(403,str(error)) from None
    except ValueError as error:raise HTTPException(400,str(error)) from None

@router.get('/account/security')
def security_page(request:Request,user=Depends(current_user)):
    return templates.TemplateResponse(request=request,name='account_security.html',context={'embedded_reauth':request.query_params.get('reauth')=='1'})

@router.get('/account/security/state')
def security_state(user=Depends(current_user),db:Session=Depends(get_db)):
    return mfa.settings(db,user.id)

@router.post('/account/security/{action:path}')
async def security_action(request:Request,action:str,user=Depends(current_user),db:Session=Depends(get_db)):
    try:
        body=await data(request)
        if action=='reauth':
            token,csrf=mfa.begin(db,user.username,body.get('password'),session_token=request.cookies[COOKIE],kind='reauth')
            return flow_cookie(request,JSONResponse({'ok':True,'redirect_to':'/auth/mfa'}),token)
        if action=='add-factor':
            token,csrf=mfa.manage_start(db,user.id,request.cookies[COOKIE]);return flow_cookie(request,JSONResponse({'ok':True,'redirect_to':'/auth/mfa'}),token)
        if action=='backup':return {'codes':mfa.backup_generate(db,user.id)}
        if action in ('remove','rename'):
            mfa.factor_change(db,user.id,body.get('kind'),body.get('id'),body.get('name') if action=='rename' else None)
            return {'ok':True,'redirect_to':'/auth/login' if action=='remove' else '/account/security'}
        raise HTTPException(404,'Невідома дія.')
    except PermissionError as error:raise HTTPException(403,str(error)) from None
    except ValueError as error:raise HTTPException(400,str(error)) from None

@router.get('/account/sessions')
def sessions_page(request:Request,user=Depends(current_user)):
    return templates.TemplateResponse(request=request,name='account_sessions.html',context={})

@router.get('/account/sessions/data')
def sessions(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    return {'sessions':mfa.own_sessions(db,user.id,request.state.personal_session.public_id)}

@router.post('/account/sessions/revoke')
async def revoke(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    body=await data(request)
    mfa.revoke_others(db,user.id,request.cookies[COOKIE],body)
    return {'ok':True}

@router.post('/account/activity')
def activity(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    try:return mfa.activity(db,user.id,request.cookies[COOKIE])
    except PermissionError as error:raise HTTPException(401,str(error)) from None

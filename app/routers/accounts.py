"""System-wide JSON authentication API; no document-specific identity logic."""
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.security.accounts import COOKIE, current_user, check_origin, secure_transport
from app.services import accounts

router = APIRouter(prefix='/auth', tags=['Accounts'])


@router.post('/login')
async def login(request: Request, db: Session = Depends(get_db)):
    secure_transport(request); check_origin(request)
    # JSON only: a cross-site HTML form cannot initiate a login.
    if request.headers.get('content-type','').split(';')[0] != 'application/json': raise HTTPException(415, 'Потрібен JSON.')
    try:data = await request.json()
    except ValueError:raise HTTPException(400,'Неправильний JSON.') from None
    if not isinstance(data, dict): raise HTTPException(400, 'Потрібен об’єкт JSON.')
    try: token, csrf = accounts.login(db, data.get('username'), data.get('password'))
    except PermissionError as error: raise HTTPException(401, str(error)) from error
    response = JSONResponse({'ok': True, 'csrf_token': csrf}, headers={'Cache-Control':'no-store'})
    response.set_cookie(COOKIE, token, httponly=True, secure=request.url.scheme=='https', samesite='strict', max_age=28800, path='/')
    return response


@router.get('/me')
def me(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    return JSONResponse(accounts.session_info(db,request.cookies[COOKIE]), headers={'Cache-Control':'no-store'})


@router.post('/logout')
def logout(request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    accounts.logout(db, request.cookies[COOKIE]); response = JSONResponse({'ok':True})
    response.delete_cookie(COOKIE, path='/'); return response


@router.post('/users')
async def create(request: Request, user=Depends(current_user), db: Session = Depends(get_db)):
    try:data = await request.json()
    except ValueError:raise HTTPException(400,'Неправильний JSON.') from None
    if not isinstance(data,dict):raise HTTPException(400,'Потрібен об’єкт JSON.')
    try:
        key = accounts.create_user(db, data.get('username'), data.get('display_name'), data.get('password'), data.get('role','viewer'), actor_id=user.id)
        return {'id':key}
    except PermissionError as error: raise HTTPException(403, str(error)) from error
    except ValueError as error: raise HTTPException(400, str(error)) from error

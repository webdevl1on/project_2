"""HTTP session policy; the legacy shared admin token never identifies a user."""
import hmac
import os
from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import accounts

COOKIE = 'project2_user'


def personal_actor(request, db):
    """Optional verified personal session; never attribute the open-mode identity."""
    check_origin(request)
    user=getattr(request.state,'authenticated_user',None)
    if user is not None:return user.id
    try:
        return accounts.authenticate(db, request.cookies.get(COOKIE, ''))[0].id
    except PermissionError:
        return None


def check_origin(request):
    origin = request.headers.get('origin')
    if (origin and origin.rstrip('/') != str(request.base_url).rstrip('/')) or request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Запит з іншого сайту заборонений.')


def secure_transport(request):
    if request.url.scheme == 'https': return
    # Explicit loopback development only; forwarded requests cannot opt in.
    # Do not inherit the admin bypass: this flag only permits HTTP, never login-free access.
    from ipaddress import ip_address
    try: local = request.client and ip_address(request.client.host).is_loopback
    except ValueError: local = False
    forwarded = any(k == 'forwarded' or k.startswith('x-forwarded-') or k in ('x-real-ip','via','cf-connecting-ip','true-client-ip') for k in request.headers)
    if os.environ.get('PROJECT2_AUTH_ALLOW_LOCAL_HTTP') != '1' or not local or request.url.hostname not in ('localhost','127.0.0.1','::1') or forwarded:
        raise HTTPException(403, 'Персональний вхід потребує HTTPS; локальний HTTP вмикається окремо.')


def dev_request(request):
    # Retained compatibility name; neither legacy flag can bypass a session.
    return False


async def current_user(request: Request, db: Session = Depends(get_db)):
    if getattr(request.state, 'authenticated_user', None) is not None:
        return request.state.authenticated_user
    secure_transport(request)
    try: user, session = accounts.authenticate(db, request.cookies.get(COOKIE, ''))
    except PermissionError as error: raise HTTPException(401, str(error), headers={'Cache-Control':'no-store'}) from error
    if request.method not in ('GET','HEAD','OPTIONS'):
        check_origin(request)
        supplied=request.headers.get('x-csrf-token')
        if supplied is None and request.headers.get('content-type','').split(';')[0] in ('application/x-www-form-urlencoded','multipart/form-data'):
            supplied=(await request.form()).get('csrf','')
        if not isinstance(supplied,str) or not hmac.compare_digest(supplied.encode(), session.csrf_token.encode()):
            raise HTTPException(403, 'Неправильний CSRF-токен.')
    request.state.authenticated_user=user
    request.state.personal_session=session
    request.state.csrf_token=session.csrf_token
    return user

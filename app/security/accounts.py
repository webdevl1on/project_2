"""HTTP session policy; the legacy shared admin token never identifies a user."""
import hmac
import os
from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import accounts

COOKIE = 'project2_user'


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
    forwarded = any(k == 'forwarded' or k.startswith('x-forwarded-') or k == 'x-real-ip' for k in request.headers)
    if os.environ.get('PROJECT2_AUTH_ALLOW_LOCAL_HTTP') != '1' or not local or request.url.hostname not in ('localhost','127.0.0.1','::1') or forwarded:
        raise HTTPException(403, 'Персональний вхід потребує HTTPS; локальний HTTP вмикається окремо.')


def current_user(request: Request, db: Session = Depends(get_db)):
    secure_transport(request)
    try: user, session = accounts.authenticate(db, request.cookies.get(COOKIE, ''))
    except PermissionError as error: raise HTTPException(401, str(error)) from error
    if request.method not in ('GET','HEAD','OPTIONS'):
        check_origin(request)
        if not hmac.compare_digest(request.headers.get('x-csrf-token',''), session.csrf_token):
            raise HTTPException(403, 'Неправильний CSRF-токен.')
    return user

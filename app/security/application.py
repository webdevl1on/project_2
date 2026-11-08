"""Default-deny access for every FastAPI route, including legacy routers."""
from urllib.parse import urlencode, urlsplit, unquote
import re
from fastapi import Request, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette._utils import get_route_path
from app.database.db import get_db
from app.security.accounts import current_user
from app.account_policy import has_role

# Only the credential entry point is public. Static assets are a separate mount.
PUBLIC_ROUTES = frozenset({('GET', '/auth/login'), ('POST', '/auth/login')})
MFA_PATHS=frozenset({'/auth/mfa','/auth/mfa/state','/auth/mfa/totp/start','/auth/mfa/totp/confirm','/auth/mfa/prove','/auth/mfa/passkey/options','/auth/mfa/passkey/verify','/auth/mfa/finish'})
SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})
ADMIN_PREFIXES = ('/admin', '/staff/import', '/staff/structures', '/staff/versions', '/staff/positions')
HTML_PATHS = frozenset({'/persons','/persons/new','/person-positions','/staff/history','/events',
    '/admin','/admin/login','/admin/staff','/admin/dictionaries','/admin/dictionaries/new',
    '/admin/tcc','/admin/tcc/new','/admin/users','/admin/users/new','/admin/users/audit','/admin/organization','/admin/organization/staff','/account/password','/account/security','/account/sessions','/docs','/redoc'})


def html_page(path):
    # Redirect only actual pages; files/JSON APIs remain 401 even with Accept: text/html.
    return path in HTML_PATHS or bool(re.fullmatch(
        r'/persons/\d+/(?:edit|created)|/person_(?:detail|full_info)/\d+|/person_name/\d+/cases|/admin/(?:dictionaries|tcc)/\d+/edit|/admin/users/\d+',path))



def safe_return(value):
    if not isinstance(value, str) or not value or len(value)>4096:return '/persons'
    decoded=value
    for _ in range(3):decoded=unquote(decoded)
    if any(ord(c)<32 or ord(c)==127 for c in decoded) or '\\' in decoded:return '/persons'
    try:parts=urlsplit(decoded)
    except ValueError:return '/persons'
    if not decoded.startswith('/') or decoded.startswith('//') or parts.scheme or parts.netloc:return '/persons'
    if parts.path.startswith('/auth/'):return '/persons'
    return value


def admin_path(path):
    return any(path==prefix or path.startswith(prefix+'/') for prefix in ADMIN_PREFIXES)


async def application_access(request: Request, db: Session = Depends(get_db)):
    # Use the router's decoded, mount-relative ASGI path for policy decisions.
    path=get_route_path(request.scope)
    if (request.method, path) in PUBLIC_ROUTES:return
    if path in MFA_PATHS:
        from app.routers.mfa import pending_request
        await pending_request(request,db)
        return
    try:
        user=await current_user(request,db)
    except HTTPException as error:
        if error.status_code==401 and request.method in ('GET','HEAD') and html_page(path) and 'text/html' in request.headers.get('accept',''):
            target=safe_return(request.url.path+('?' + request.url.query if request.url.query else ''))
            raise HTTPException(303,'Потрібен персональний вхід.',headers={'Location':'/auth/login?'+urlencode({'return_to':target}),'Cache-Control':'no-store'}) from error
        raise
    if admin_path(path) or path=='/auth/users':
        if not has_role(user,('admin',)):raise HTTPException(403,'Потрібні права адміністратора.')
    elif request.method not in SAFE_METHODS and path not in ('/auth/logout','/auth/password') and not path.startswith('/account/') and not has_role(user,('admin','editor')):
        raise HTTPException(403,'Потрібні права редактора.')

    if request.method not in SAFE_METHODS and (path=='/auth/password' or path=='/auth/users' or path.startswith('/admin/users') or path.startswith('/account/security/')) and path!='/account/security/reauth':
        from app.services.mfa import fresh
        if not fresh(request.state.personal_session):raise HTTPException(403,'MFA_REAUTH_REQUIRED: повторно підтвердьте пароль і MFA на /account/security.')

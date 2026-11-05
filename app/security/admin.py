"""Administration belongs to a verified personal admin session, never a token."""
import hmac
from fastapi import HTTPException, Request


class AdminOwner(str):
    """Serializable preview owner tied to one personal session."""
    def __new__(cls, value, csrf):
        owner=super().__new__(cls,value);owner.csrf=csrf
        return owner


def require_admin(request: Request):
    user=getattr(request.state,'authenticated_user',None)
    session=getattr(request.state,'personal_session',None)
    if user is None or session is None:raise HTTPException(401,'Потрібен персональний вхід.')
    if user.role!='admin':raise HTTPException(403,'Потрібні права адміністратора.')
    return AdminOwner(f'user:{user.id}:session:{session.token_hash}',session.csrf_token)


def csrf_token(owner):
    if not isinstance(owner,AdminOwner):raise HTTPException(401,'Потрібна персональна сесія адміністратора.')
    return owner.csrf


def check_csrf(owner, token):
    if not hmac.compare_digest(csrf_token(owner).encode(),(token or '').encode()):
        raise HTTPException(403,'Невірний CSRF-токен. Оновіть сторінку.')

"""Reusable identity/session services, not owned by the documents module."""
from datetime import datetime, UTC, timedelta
import hashlib
import hmac
import re
import secrets
from app.database.transactions import service_transaction
from app.models.accounts import User, UserSession
from app.repositories.account_repository import AccountRepository as Repo


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 128:
        raise ValueError('Пароль повинен містити 12–128 символів.')
    salt = secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return f'scrypt${salt}${digest}'


def verify_password(password, encoded):
    if not isinstance(password, str) or len(password) > 128: return False
    try:
        algorithm, salt, digest = encoded.split('$')
        if algorithm != 'scrypt': return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
        return hmac.compare_digest(actual, digest)
    except (ValueError, TypeError): return False


def digest_token(token): return hashlib.sha256(token.encode()).hexdigest()


def authorize(db, user_id, roles=('admin', 'editor', 'viewer')):
    user = Repo.user(db, user_id)
    # Always re-read: permissions may have changed since the request started.
    if user is not None: db.refresh(user)
    if user is None or not user.is_active or user.role not in roles:
        raise PermissionError('Недостатньо прав або обліковий запис вимкнено.')
    return user


def create_user(db, username, display_name, password, role='viewer', *, actor_id=None):
    if not isinstance(username,str) or not isinstance(display_name,str): raise ValueError('Логін та ім’я повинні бути текстом.')
    username = (username or '').strip().casefold()
    if not re.fullmatch(r'[a-z0-9_.-]{3,100}', username):
        raise ValueError('Логін: 3–100 латинських літер, цифр, крапка, _ або дефіс.')
    if role not in ('admin','editor','viewer') or not (display_name or '').strip() or len(display_name) > 200:
        raise ValueError('Вкажіть ім’я користувача та коректну роль.')
    encoded = password_hash(password)
    with service_transaction(db, immediate=True):
        if actor_id is None:
            if Repo.count(db) or role != 'admin': raise PermissionError('Початкове створення дозволено тільки для першого адміністратора.')
        else: authorize(db, actor_id, ('admin',))
        if Repo.by_name(db, username): raise ValueError('Логін уже зайнятий.')
        user = Repo.add(db, User(username=username, display_name=display_name.strip(), password_hash=encoded, role=role))
        db.flush(); key = user.id
    return key


def login(db, username, password):
    if not isinstance(username,str): raise PermissionError('Неправильний логін або пароль.')
    denied=False;token=csrf=None
    with service_transaction(db, immediate=True):
        user = Repo.by_name(db, (username or '').strip().casefold())
        # Apply the same expensive operation for unknown logins.
        encoded = user.password_hash if user else 'scrypt$' + '00'*16 + '$' + '00'*64
        valid = verify_password(password, encoded)
        locked=user and user.locked_until and user.locked_until.replace(tzinfo=UTC)>datetime.now(UTC)
        if not valid or user is None or not user.is_active or locked:
            denied=True
            if user and user.is_active and not locked:
                user.failed_attempts+=1
                if user.failed_attempts>=5:
                    user.locked_until=datetime.now(UTC)+timedelta(minutes=5);user.failed_attempts=0
        else:
            user.failed_attempts=0;user.locked_until=None
            token = secrets.token_urlsafe(48); csrf = secrets.token_hex(32)
            Repo.add(db, UserSession(token_hash=digest_token(token), user_id=user.id, csrf_token=csrf,
                                     expires_at=datetime.now(UTC) + timedelta(hours=8)))
    # Failed-attempt counters must commit, unlike a rejected business write.
    if denied:raise PermissionError('Неправильний логін або пароль або тимчасове блокування входу.')
    return token, csrf


def authenticate(db, token):
    session = Repo.session(db, digest_token(token)) if token and len(token) < 200 else None
    if session is None or session.expires_at.replace(tzinfo=UTC) <= datetime.now(UTC):
        raise PermissionError('Потрібен персональний вхід.')
    user = authorize(db, session.user_id)
    return user, session


def session_info(db,token):
    user,session=authenticate(db,token)
    return {'id':user.id,'username':user.username,'display_name':user.display_name,'role':user.role,'csrf_token':session.csrf_token}


def logout(db, token):
    with service_transaction(db, immediate=True):
        session = Repo.session(db, digest_token(token))
        if session: Repo.delete(db, session)

"""Reusable identity/session services, not owned by the documents module."""
from datetime import datetime, UTC, timedelta
from contextlib import contextmanager
import hashlib
import hmac
import re
import secrets
from app.database.transactions import service_transaction
from app.models.accounts import User, UserSession, AccountAudit
from app.account_policy import has_role, personal
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
    if user is None or not user.is_active or not has_role(user, roles):
        raise PermissionError('Недостатньо прав або обліковий запис вимкнено.')
    return user


def create_user(db, username, display_name, password, role='viewer', *, actor_id=None, allow_legacy_bootstrap=False):
    if not isinstance(username,str) or not isinstance(display_name,str): raise ValueError('Логін та ім’я повинні бути текстом.')
    username = (username or '').strip().casefold()
    if not re.fullmatch(r'[a-z0-9_.-]{3,100}', username):
        raise ValueError('Логін: 3–100 латинських літер, цифр, крапка, _ або дефіс.')
    if role not in ('admin','editor','viewer') or not (display_name or '').strip() or len(display_name) > 200:
        raise ValueError('Вкажіть ім’я користувача та коректну роль.')
    encoded = password_hash(password)
    with account_write(db):
        if actor_id is None:
            existing=Repo.bootstrap_accounts(db)
            # CLI-only opt-in: preserve the exact legacy technical identities.
            def technical(user):
                known={'project2-open-access':('admin','Спільний автор — авторизацію вимкнено','open-access-only$'),
                       'project2-dev-local':('editor','Локальна розробка (тестовий автор)','dev-only$')}
                expected=known.get(user.username)
                return expected and (user.role,user.display_name)==expected[:2] and user.password_hash.startswith(expected[2])
            if role!='admin' or (existing and not (allow_legacy_bootstrap and all(technical(user) for user in existing))):
                raise PermissionError('Початкове створення дозволено тільки для першого персонального адміністратора. Для незмінених технічних записів є явний CLI-параметр --allow-legacy-technical-accounts.')
        else: authorize(db, actor_id, ('admin',))
        if Repo.by_name(db, username): raise ValueError('Логін уже зайнятий.')
        user = Repo.add(db, User(username=username, display_name=display_name.strip(), password_hash=encoded, role=role))
        db.flush(); key = user.id
        audit_change(db,user,'create',{},actor_id)
    return key


def login(db, username, password):
    from app.services.mfa import begin
    return begin(db,username,password)


def authenticate(db, token):
    session = Repo.session(db, digest_token(token)) if token and len(token) < 200 else None
    from app.services.mfa import live
    if not live(session):
        raise PermissionError('Потрібен персональний вхід.')
    user = authorize(db, session.user_id)
    return user, session


def session_info(db,token):
    user,session=authenticate(db,token)
    return {'id':user.id,'username':user.username,'display_name':user.display_name,'role':user.role,'csrf_token':session.csrf_token,'idle_expires_at':(session.last_activity+timedelta(minutes=15)).isoformat()+'Z','expires_at':session.expires_at.isoformat()+'Z'}


def logout(db, token):
    with account_write(db):
        session = Repo.session(db, digest_token(token))
        if session: Repo.delete(db, session)


@contextmanager
def account_write(db):
    with service_transaction(db,immediate=True):
        Repo.lock_management(db)
        yield


def account_snapshot(user):
    return {field:getattr(user,field) for field in ('id','username','display_name','role','is_active','revision')}


def audit_change(db,user,operation,before,actor_id,reason=None,**details):
    db.flush()
    after={**account_snapshot(user),**details}
    db.add(AccountAudit(user_id=user.id,actor_user_id=actor_id,operation=operation,
                        before=before,after=after,reason=reason))
    db.flush()


def management_target(db,actor_id,key,revision):
    actor=authorize(db,actor_id,('admin',))
    user=Repo.locked_user(db,key)
    if user is None:raise ValueError('Обліковий запис не існує.')
    if not personal(user):raise PermissionError('Технічний історичний запис не редагується; створіть персональний обліковий запис.')
    if user.role=='master' and actor.role!='master':raise PermissionError('Admin не може змінювати Master.')
    if user.revision!=revision:raise ValueError('Обліковий запис змінився. Оновіть сторінку.')
    return actor,user


def checked_reason(reason):
    if not isinstance(reason,(str,type(None))):raise ValueError('Причина має бути текстом.')
    reason=(reason or '').strip()
    if len(reason)>2000:raise ValueError('Причина: максимум 2000 символів.')
    return reason or None


def keep_admin(db,user,role,active):
    if user.role=='master' and (role!='master' or not active):raise ValueError('Master не може втратити роль або бути вимкненим.')
    if user.role=='admin' and user.is_active and (role!='admin' or not active) and Repo.active_admins(db)<=1:
        raise ValueError('Не можна вимкнути або понизити останнього активного персонального Admin.')


def update_user(db,actor_id,key,revision,*,display_name=None,role=None,reason=None,confirmed=False):
    reason=checked_reason(reason)
    with account_write(db):
        actor,user=management_target(db,actor_id,key,revision)
        role=user.role if role is None else role
        if role=='master' and user.role!='master':raise ValueError('Master призначається лише одноразовою CLI-процедурою.')
        if role not in ('master','admin','editor','viewer'):raise ValueError('Невідома роль.')
        keep_admin(db,user,role,user.is_active)
        if display_name is not None and (not isinstance(display_name,str) or not display_name.strip() or len(display_name)>200):raise ValueError('Вкажіть відображуване ім’я до 200 символів.')
        before=account_snapshot(user)
        changed_role=user.role!=role
        if changed_role and not confirmed:raise ValueError('Підтвердьте зміну ролі.')
        user.role=role
        if display_name is not None:user.display_name=display_name.strip()
        db.flush()
        if before!=account_snapshot(user):audit_change(db,user,'role_change' if changed_role else 'edit',before,actor_id,reason)
    return key


def set_active(db,actor_id,key,revision,active,*,confirmed=False,reason=None):
    if not confirmed:raise ValueError('Підтвердьте зміну статусу користувача.')
    if type(active) is not bool:raise ValueError('Статус має бути логічним значенням.')
    reason=checked_reason(reason)
    with account_write(db):
        _,user=management_target(db,actor_id,key,revision)
        keep_admin(db,user,user.role,active)
        if user.is_active==active:raise ValueError('Користувач уже має цей статус.')
        before=account_snapshot(user);user.is_active=active
        revoked=Repo.revoke_sessions(db,key) if not active else 0
        audit_change(db,user,'unblock' if active else 'block',before,actor_id,reason,revoked_sessions=revoked)
    return key


def new_password(password,confirmation,old_hash):
    if password!=confirmation:raise ValueError('Підтвердження нового пароля не збігається.')
    encoded=password_hash(password)
    if verify_password(password,old_hash):raise ValueError('Новий пароль має відрізнятися від поточного.')
    return encoded


def change_password(db,actor_id,current,password,confirmation):
    with account_write(db):
        user=authorize(db,actor_id)
        user=Repo.locked_user(db,user.id)
        if not verify_password(current,user.password_hash):raise ValueError('Неправильний поточний пароль.')
        encoded=new_password(password,confirmation,user.password_hash)
        before=account_snapshot(user);user.password_hash=encoded
        revoked=Repo.revoke_sessions(db,user.id)
        audit_change(db,user,'password_change',before,actor_id,password_changed=True,revoked_sessions=revoked)
    return actor_id


def reset_password(db,actor_id,key,revision,password,confirmation,*,confirmed=False,reason=None):
    if not confirmed:raise ValueError('Підтвердьте скидання пароля.')
    if actor_id==key:raise ValueError('Власний пароль змінюється з перевіркою поточного пароля.')
    reason=checked_reason(reason)
    with account_write(db):
        _,user=management_target(db,actor_id,key,revision)
        if user.role=='master':raise PermissionError('Адміністративне скидання пароля Master заборонене.')
        encoded=new_password(password,confirmation,user.password_hash)
        before=account_snapshot(user);user.password_hash=encoded
        revoked=Repo.revoke_sessions(db,key)
        audit_change(db,user,'password_reset',before,actor_id,reason,password_changed=True,revoked_sessions=revoked)
    return key


def revoke_all_sessions(db,actor_id,key,revision,*,confirmed=False,reason=None):
    if not confirmed:raise ValueError('Підтвердьте завершення всіх сесій.')
    reason=checked_reason(reason)
    with account_write(db):
        _,user=management_target(db,actor_id,key,revision)
        before=account_snapshot(user);revoked=Repo.revoke_sessions(db,key)
        user.revision+=1
        audit_change(db,user,'sessions_revoke',before,actor_id,reason,revoked_sessions=revoked)
    return key


def promotion_target(db,key):
    user=Repo.locked_user(db,key)
    if user is None or user.role!='admin' or not user.is_active or not personal(user):
        raise ValueError('Потрібен чинний персональний Admin за явно зазначеним ID.')
    if user.locked_until and user.locked_until.replace(tzinfo=UTC)>datetime.now(UTC):raise ValueError('Вхід цього Admin тимчасово заблокований; дочекайтеся завершення блокування.')
    if Repo.master(db):raise ValueError('Master уже існує. Повторне призначення заборонене.')
    return user


def promote_master(db,key,password,*,confirmed=False,expected_revision=None):
    if not confirmed:raise ValueError('Потрібне явне підтвердження початкового призначення Master.')
    with account_write(db):
        user=promotion_target(db,key)
        if expected_revision is not None and user.revision!=expected_revision:raise ValueError('Запис змінився після попередньої перевірки.')
        if not verify_password(password,user.password_hash):raise ValueError('Неправильний пароль цільового Admin.')
        before=account_snapshot(user);user.role='master'
        audit_change(db,user,'promote_master',before,user.id,'Початкове призначення Master через захищену CLI-процедуру')
    return key

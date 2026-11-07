"""MFA operations serialized in the existing account write unit, with safe audit."""
from datetime import datetime,UTC,timedelta
import secrets,hashlib,hmac,json
import pyotp
from webauthn.helpers import exceptions as webauthn_errors
VERIFY_ERRORS=(ValueError,TypeError,KeyError,AttributeError)+tuple(value for name,value in vars(webauthn_errors).items() if isinstance(value,type) and issubclass(value,Exception))
from webauthn import generate_registration_options,generate_authentication_options,verify_registration_response,verify_authentication_response,options_to_json
from webauthn.helpers import bytes_to_base64url,base64url_to_bytes
from webauthn.helpers.structs import AuthenticatorSelectionCriteria,UserVerificationRequirement,PublicKeyCredentialDescriptor
from app.models.accounts import UserSession
from app.models.mfa import AuthFlow,TotpFactor,Passkey,RecoveryCode
from app.repositories.mfa_repository import MfaRepository as Repo
from app.services import accounts
from app.security.mfa_config import require_keys,encrypt,decrypt,relying_party

TTL=timedelta(minutes=5)
IDLE=timedelta(minutes=15)
FRESH=timedelta(minutes=5)

def now():return datetime.now(UTC).replace(tzinfo=None)

def live(session):
    return bool(session and session.mfa_verified_at and session.created_at and session.last_activity and session.expires_at>now() and session.created_at+timedelta(hours=8)>now() and session.last_activity+IDLE>now())

def fresh(session):return live(session) and session.mfa_verified_at+FRESH>now()

def audit(db,uid,operation,actor=None,**values):
    user=accounts.Repo.user(db,uid)
    accounts.audit_change(db,user,operation,{},uid if actor is None else actor,**values)

def configured(db,uid):return bool(Repo.totp(db,uid) or Repo.passkeys(db,uid))

def new_flow(db,user,kind,*,session=None,return_to='/persons'):
    token=secrets.token_urlsafe(48);csrf=secrets.token_hex(32)
    row=AuthFlow(token_hash=accounts.digest_token(token),user_id=user.id,csrf_token=csrf,kind=kind,
                 password_stamp=accounts.digest_token(user.password_hash),session_hash=session.token_hash if session else None,
                 expires_at=now()+TTL,return_to=return_to)
    db.add(row);db.flush();return token,csrf

def pending(db,token):
    flow=Repo.flow(db,accounts.digest_token(token)) if isinstance(token,str) and len(token)<200 else None
    if not flow or flow.consumed or flow.expires_at<=now() or flow.attempts>=5:raise PermissionError('Етап входу завершився. Почніть вхід знову.')
    user=accounts.authorize(db,flow.user_id)
    if not hmac.compare_digest(flow.password_stamp,accounts.digest_token(user.password_hash)) or (user.locked_until and user.locked_until.replace(tzinfo=None)>now()):raise PermissionError('Підтвердження входу недійсне або тимчасово заблоковане.')
    if flow.session_hash:
        session=accounts.Repo.session(db,flow.session_hash)
        if not live(session) or session.user_id!=user.id:raise PermissionError('Сесія завершилася.')
        if flow.kind=='manage' and not fresh(session):raise PermissionError('Повторно підтвердьте пароль і MFA; свіже підтвердження завершилося.')
    return user,flow

def begin(db,username,password,return_to='/persons',session_token=None,kind=None):
    # Password failure counters are committed even when authentication fails.
    denied=False;result=None
    with accounts.account_write(db):
        require_keys(db)
        user=accounts.Repo.by_name(db,username.strip().casefold()) if isinstance(username,str) else None
        valid=accounts.verify_password(password,user.password_hash if user else 'scrypt$'+'00'*16+'$'+'00'*64)
        locked=user and user.locked_until and user.locked_until.replace(tzinfo=None)>now()
        if not user or not valid or not user.is_active or locked:
            denied=True
            if user and user.is_active and not locked:failure_user(user)
        else:
            session=None
            if session_token:
                session=accounts.Repo.session(db,accounts.digest_token(session_token))
                if not live(session) or session.user_id!=user.id:raise PermissionError('Потрібна чинна власна сесія.')
            result=new_flow(db,user,kind or ('login' if configured(db,user.id) else 'setup'),session=session,return_to=return_to)
    if denied:raise PermissionError('Неправильний логін або пароль або тимчасове блокування входу.')
    return result

def failure_user(user):
    user.failed_attempts+=1
    if user.failed_attempts>=5:user.locked_until=now()+TTL;user.failed_attempts=0

def failure(db,user,flow):
    flow.attempts+=1;failure_user(user)

def state(db,token):
    user,flow=pending(db,token)
    return {'csrf_token':flow.csrf_token,'kind':flow.kind,'verified':flow.verified,'has_totp':bool(Repo.totp(db,user.id)),
            'has_passkey':bool(Repo.passkeys(db,user.id)),'username':user.username}

def totp_start(db,token):
    with accounts.account_write(db):
        user,flow=pending(db,token)
        if flow.kind not in ('setup','manage') or flow.verified or (flow.kind=='setup' and Repo.totp(db,user.id)):raise ValueError('Налаштування TOTP недоступне.')
        secret=pyotp.random_base32();flow.ciphertext=encrypt(secret)
        return {'secret':secret,'uri':pyotp.TOTP(secret).provisioning_uri(user.username,issuer_name='project_2')}

def totp_step(secret,code,last=-1):
    if not isinstance(code,str) or len(code)!=6 or not code.isascii() or not code.isdigit():return None
    current=int(now().replace(tzinfo=UTC).timestamp())//30
    for step in (current,current-1,current+1):
        if step>last and hmac.compare_digest(pyotp.TOTP(secret).at(step*30),code):return step
    return None

def regenerate(db,uid):
    Repo.clear_codes(db,uid)
    codes=[secrets.token_hex(12) for _ in range(10)]
    db.add_all([RecoveryCode(user_id=uid,digest=accounts.digest_token(code)) for code in codes]);return codes

def verified(db,user,flow,enrolling=False):
    flow.verified=True;user.failed_attempts=0;user.locked_until=None
    if enrolling:
        flow.ciphertext=None
        audit(db,user.id,'mfa_enroll' if flow.kind=='setup' else 'factor_add',factor_kind=enrolling)
        if flow.kind=='setup':
            Repo.invalidate_flows(db,user.id,flow.token_hash)
            return {'ok':True,'codes':regenerate(db,user.id)}
    return {'ok':True}

def totp_confirm(db,token,code):
    result=None;denied=False
    with accounts.account_write(db):
        user,flow=pending(db,token)
        if flow.kind=='setup' and configured(db,user.id):raise PermissionError('MFA вже налаштовано; увійдіть знову.')
        if flow.verified or flow.kind not in ('setup','manage') or not flow.ciphertext:raise ValueError('Спочатку почніть налаштування TOTP.')
        step=totp_step(decrypt(flow.ciphertext),code)
        if step is None:failure(db,user,flow);denied=True
        else:
            existing=Repo.totp(db,user.id)
            if existing:existing.ciphertext=flow.ciphertext;existing.last_step=step
            else:db.add(TotpFactor(user_id=user.id,ciphertext=flow.ciphertext,last_step=step))
            result=verified(db,user,flow,'totp')
            if existing:
                accounts.Repo.revoke_sessions(db,user.id)
                result={'ok':True,'redirect_to':'/auth/login'}
    if denied:raise PermissionError('Неправильний або повторний код MFA.')
    return result

def prove(db,token,method,code):
    denied=False
    with accounts.account_write(db):
        user,flow=pending(db,token)
        if flow.kind not in ('login','reauth') or flow.verified:raise PermissionError('Невідповідний етап MFA.')
        factor=Repo.totp(db,user.id);step=None;recovery=None
        if method=='totp' and factor:step=totp_step(decrypt(factor.ciphertext),code,factor.last_step)
        elif method=='backup' and isinstance(code,str) and len(code)<=100:
            recovery=next((r for r in Repo.codes(db,user.id) if hmac.compare_digest(r.digest,accounts.digest_token(code.strip()))),None)
        if step is None and recovery is None:failure(db,user,flow);denied=True
        else:
            if recovery:db.delete(recovery);audit(db,user.id,'backup_use')
            else:factor.last_step=step
            verified(db,user,flow)
    if denied:raise PermissionError('Неправильний або повторний код MFA.')
    return {'ok':True,'recovery':method=='backup'}

def passkey_options(db,token,register=False):
    with accounts.account_write(db):
        user,flow=pending(db,token);rp,origins=relying_party()
        if flow.verified:raise ValueError('Фактор уже підтверджено.')
        keys=Repo.passkeys(db,user.id);descriptors=[PublicKeyCredentialDescriptor(id=k.credential_id) for k in keys]
        if register:
            if flow.kind not in ('setup','manage'):raise PermissionError('Невідповідний етап реєстрації.')
            opts=generate_registration_options(rp_id=rp,rp_name='project_2',user_id=str(user.id).encode(),user_name=user.username,
                exclude_credentials=descriptors,authenticator_selection=AuthenticatorSelectionCriteria(user_verification=UserVerificationRequirement.REQUIRED))
        else:
            if flow.kind not in ('login','reauth') or not keys:raise PermissionError('Passkey недоступний.')
            opts=generate_authentication_options(rp_id=rp,allow_credentials=descriptors,user_verification=UserVerificationRequirement.REQUIRED)
        data=json.loads(options_to_json(opts));flow.challenge={'value':data['challenge'],'register':register};return data

def passkey_verify(db,token,credential,register=False,name='Passkey'):
    denied=False;result=None
    with accounts.account_write(db):
        user,flow=pending(db,token);rp,origins=relying_party();challenge=flow.challenge;flow.challenge=None
        if register and flow.kind=='setup' and configured(db,user.id):raise PermissionError('MFA вже налаштовано; увійдіть знову.')
        if flow.verified or not challenge or challenge['register']!=register:raise PermissionError('Challenge відсутній або вже використаний.')
        try:
            expected=base64url_to_bytes(challenge['value'])
            if register:
                if flow.kind not in ('setup','manage') or not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError()
                response=verify_registration_response(credential=credential,expected_challenge=expected,expected_rp_id=rp,expected_origin=origins,require_user_verification=True)

            else:
                if flow.kind not in ('login','reauth'):raise ValueError()
                key=next((key for key in Repo.passkeys(db,user.id) if bytes_to_base64url(key.credential_id)==credential.get('id')),None)
                if key is None:raise ValueError()
                response=verify_authentication_response(credential=credential,expected_challenge=expected,expected_rp_id=rp,expected_origin=origins,
                    credential_public_key=key.public_key,credential_current_sign_count=key.sign_count,require_user_verification=True)

        except VERIFY_ERRORS:
            # Validation errors consume the challenge. Storage/audit failures propagate and roll back.
            failure(db,user,flow);denied=True
        if not denied:
            if register:db.add(Passkey(user_id=user.id,credential_id=response.credential_id,public_key=response.credential_public_key,sign_count=response.sign_count,name=name.strip()))
            else:key.sign_count=response.new_sign_count
            result=verified(db,user,flow,'passkey' if register else False)
    if denied:raise PermissionError('Passkey не пройшов криптографічну перевірку.')
    return result

def finish(db,token):
    with accounts.account_write(db):
        user,flow=pending(db,token)
        if not flow.verified or not configured(db,user.id):raise PermissionError('Спочатку підтвердьте MFA.')
        flow.consumed=True
        if flow.kind in ('manage','reauth'):
            session=accounts.Repo.session(db,flow.session_hash)
            if not live(session):raise PermissionError('Сесія завершилася.')
            if flow.kind=='reauth':session.mfa_verified_at=now();audit(db,user.id,'mfa_reauth')
            return {'ok':True,'redirect_to':'/account/security'}
        token=secrets.token_urlsafe(48);csrf=secrets.token_hex(32);at=now()
        db.add(UserSession(token_hash=accounts.digest_token(token),user_id=user.id,csrf_token=csrf,public_id=secrets.token_hex(16),created_at=at,last_activity=at,mfa_verified_at=at,expires_at=at+timedelta(hours=8)))
        return {'ok':True,'token':token,'csrf_token':csrf,'redirect_to':flow.return_to}

def settings(db,uid):
    return {'totp':bool(Repo.totp(db,uid)),'passkeys':[{'id':k.id,'name':k.name} for k in Repo.passkeys(db,uid)],'backup_count':len(Repo.codes(db,uid))}

def manage_start(db,uid,session_token):
    with accounts.account_write(db):
        user=accounts.authorize(db,uid);session=accounts.Repo.session(db,accounts.digest_token(session_token))
        if not fresh(session) or session.user_id!=uid:raise PermissionError('Повторно підтвердьте пароль і MFA.')
        return new_flow(db,user,'manage',session=session)

def factor_change(db,uid,kind,key=None,name=None):
    if kind not in ('totp','passkey'):raise ValueError('Невідомий вид фактора.')
    with accounts.account_write(db):
        accounts.authorize(db,uid)
        if kind=='totp':factor=Repo.totp(db,uid)
        else:factor=next((k for k in Repo.passkeys(db,uid) if k.id==key),None)
        if factor is None:raise ValueError('Фактор не знайдено.')
        if name is not None:
            if kind!='passkey' or not isinstance(name,str) or not name.strip() or len(name)>100:raise ValueError('Назва до 100 символів.')
            factor.name=name.strip();audit(db,uid,'factor_add',renamed=True,factor_kind=kind,factor_id=factor.id);return
        if int(bool(Repo.totp(db,uid)))+len(Repo.passkeys(db,uid))<=1:raise ValueError('Спочатку додайте інший фактор. Останній фактор видалити не можна.')
        db.delete(factor);accounts.Repo.revoke_sessions(db,uid);audit(db,uid,'factor_remove',factor_kind=kind,factor_id=factor.id)

def backup_generate(db,uid):
    with accounts.account_write(db):
        accounts.authorize(db,uid);codes=regenerate(db,uid);audit(db,uid,'backup_generate');return codes

def recover(db,actor_id,uid,reason,*,password=None):
    reason=accounts.checked_reason(reason)
    if not reason:raise ValueError('Обов’язково задокументуйте перевірку особи та причину.')
    with accounts.account_write(db):
        if actor_id is not None:
            actor=accounts.authorize(db,actor_id,('admin',));user=accounts.authorize(db,uid)
            from app.account_policy import personal
            if not personal(user):raise PermissionError('Історичний технічний запис не змінюється.')
            if uid==actor_id or user.role=='master':raise PermissionError('Власне MFA або MFA Master не скидається через адміністративний HTTP API.')
        else:
            user=accounts.authorize(db,uid)
            if not accounts.verify_password(password,user.password_hash):raise PermissionError('Поточний пароль Master не підтверджений.')
            if user.role!='master':raise PermissionError('Серверна процедура призначена лише для Master.')
        Repo.clear_factors(db,uid);accounts.Repo.revoke_sessions(db,uid)
        accounts.audit_change(db,user,'mfa_recover',{},actor_id,reason)


def own_sessions(db,uid,current):
    accounts.authorize(db,uid)
    return [{'id':s.public_id,'created_at':s.created_at.isoformat()+'Z','last_activity':s.last_activity.isoformat()+'Z','expires_at':s.expires_at.isoformat()+'Z','current':s.public_id==current} for s in Repo.sessions(db,uid) if live(s)]

def revoke_others(db,uid,current_token,body):
    with accounts.account_write(db):
        accounts.authorize(db,uid)
        current=accounts.digest_token(current_token);count=0
        for session in Repo.sessions(db,uid):
            if session.token_hash!=current and (body.get('all_others') is True or session.public_id==body.get('id')):db.delete(session);count+=1
        audit(db,uid,'sessions_revoke',revoked_sessions=count)

def activity(db,uid,token):
    with accounts.account_write(db):
        accounts.authorize(db,uid)
        session=accounts.Repo.session(db,accounts.digest_token(token))
        if not live(session) or session.user_id!=uid:raise PermissionError('Сесія завершилася.')
        if session.last_activity<now():session.last_activity=now()
        deadline=(session.last_activity+IDLE).isoformat()+'Z'
    return {'ok':True,'idle_expires_at':deadline}

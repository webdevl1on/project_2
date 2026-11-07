"""Stable encryption key ring and explicit WebAuthn relying-party configuration."""
import json,os
from urllib.parse import urlsplit
from cryptography.fernet import Fernet,InvalidToken
from app.models.mfa import MfaKeyState

MARKER='project2 MFA key verification v1'

def keyring():
    try:
        keys=json.loads(os.environ['PROJECT2_MFA_KEYS']);current=os.environ['PROJECT2_MFA_CURRENT_KEY']
        ring={key:Fernet(value.encode()) for key,value in keys.items()}
        if not current or ':' in current or current not in ring:raise ValueError()
        return current,ring
    except (KeyError,ValueError,TypeError,AttributeError):raise ValueError('Налаштуйте стабільний PROJECT2_MFA_KEYS та PROJECT2_MFA_CURRENT_KEY.') from None

def encrypt(value):
    key,ring=keyring();return key+':'+ring[key].encrypt(value.encode()).decode()

def decrypt(value):
    try:
        key,token=value.split(':',1);return keyring()[1][key].decrypt(token.encode()).decode()
    except (KeyError,InvalidToken,ValueError):raise ValueError('Ключ MFA відсутній або не відповідає БД. Відновіть правильний key ring.') from None

def require_keys(db):
    row=db.get(MfaKeyState,1)
    if row is None or decrypt(row.ciphertext)!=MARKER:raise ValueError('Спочатку виконайте python -m app.services.mfa_keys --initialize з постійним ключем MFA.')

def relying_party():
    rp=os.environ.get('PROJECT2_WEBAUTHN_RP_ID','');origins=json.loads(os.environ.get('PROJECT2_WEBAUTHN_ORIGINS','[]'))
    if not rp or ':' in rp or '/' in rp or not isinstance(origins,list) or not origins:raise ValueError('Налаштуйте RP ID і дозволені origins WebAuthn.')
    from ipaddress import ip_address
    try:ip_address(rp)
    except ValueError:pass
    else:raise ValueError('WebAuthn RP ID має бути DNS-іменем; локально використовуйте localhost.')
    for origin in origins:
        parsed=urlsplit(origin)
        if parsed.path or parsed.query or parsed.fragment or parsed.username or not parsed.hostname or not (parsed.hostname==rp or parsed.hostname.endswith('.'+rp)) or (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in ('localhost','127.0.0.1','::1'))):raise ValueError('Некоректний origin WebAuthn; LAN потребує HTTPS.')
    return rp,origins

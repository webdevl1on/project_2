"""Explicit synthetic MFA fixtures, never imported by the application."""
import secrets
from app.services import accounts,mfa
from app.models.mfa import RecoveryCode

# Both first enrollment and subsequent login run the actual MFA service.
def verify_flow(db,token):
    user,flow=mfa.pending(db,token)
    if flow.kind=='setup':
        import pyotp
        from datetime import UTC
        setup=mfa.totp_start(db,token)
        mfa.totp_confirm(db,token,pyotp.TOTP(setup['secret']).at(mfa.now().replace(tzinfo=UTC)))
    else:
        code=secrets.token_hex(12)
        db.add(RecoveryCode(user_id=user.id,digest=accounts.digest_token(code)));db.commit()
        mfa.prove(db,token,'backup',code)

def login(db,username,password):
    token,csrf=accounts.login(db,username,password);verify_flow(db,token);result=mfa.finish(db,token)
    return result['token'],result['csrf_token']

def finish_http(client,response,factory=None):
    if response.status_code!=200:return response
    from app.main import app
    from app.database.db import get_db
    from app.security.accounts import COOKIE
    dependency=app.dependency_overrides[get_db]() if factory is None else None
    db=next(dependency) if dependency else factory()
    try:
        token=client.cookies.get('project2_pending');verify_flow(db,token)
    finally:
        if dependency:dependency.close()
        else:db.close()
    result=client.post('/auth/mfa/finish',json={},headers={'X-CSRF-Token':response.json()['csrf_token']})
    assert result.status_code==200,result.text
    return result

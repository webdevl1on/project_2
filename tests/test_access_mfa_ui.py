"""Verified Passkey freshness uses the existing five-minute policy and real signatures."""
from datetime import timedelta
from app.services import accounts,mfa
from tests.test_mfa import prepared,registration,assertion,PASSWORD


def test_passkey_session_is_fresh_until_five_minutes_and_reauth_keeps_expiry(prepared):
    client,factory,uid,clock=prepared
    with factory() as db:
        token,_=accounts.login(db,'mfa-admin',PASSWORD)
        private,credential,response=registration(mfa.passkey_options(db,token,True))
        mfa.passkey_verify(db,token,response,True,'Тестовий Passkey');mfa.finish(db,token)
        token,_=accounts.login(db,'mfa-admin',PASSWORD)
        mfa.passkey_verify(db,token,assertion(mfa.passkey_options(db,token),private,credential))
        session=mfa.finish(db,token)
    client.cookies.set('project2_user',session['token']);headers={'X-CSRF-Token':session['csrf_token']}
    def create(name,headers=headers):
        return client.post('/admin/access/templates',json={'name':name,'rules':[],'reason':'Синтетична перевірка'},headers=headers)
    assert create('Одразу після Passkey').status_code==200
    clock[0]+=timedelta(minutes=5)-timedelta(microseconds=1)
    assert create('До межі').status_code==200
    clock[0]+=timedelta(microseconds=1)
    expired=create('На межі');assert expired.status_code==403
    assert expired.json()['detail'].startswith('MFA_REAUTH_REQUIRED')
    with factory() as db:
        record=accounts.Repo.session(db,accounts.digest_token(session['token']));absolute=record.expires_at;created=record.created_at
        # Use a second cryptographically verified assertion; counter must increase.
        pending,_=mfa.begin(db,'mfa-admin',PASSWORD,session_token=session['token'],kind='reauth')
        options=mfa.passkey_options(db,pending)
        from tests.test_mfa import b64
        import hashlib,json
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        auth=hashlib.sha256(b'testserver').digest()+bytes([5])+(2).to_bytes(4,'big')
        client_data=json.dumps({'type':'webauthn.get','challenge':options['challenge'],'origin':'https://testserver'}).encode()
        proof={'id':b64(credential),'rawId':b64(credential),'type':'public-key','response':{'clientDataJSON':b64(client_data),'authenticatorData':b64(auth),'signature':b64(private.sign(auth+hashlib.sha256(client_data).digest(),ec.ECDSA(hashes.SHA256())))}}
        mfa.passkey_verify(db,pending,proof);mfa.finish(db,pending)
        record=accounts.Repo.session(db,accounts.digest_token(session['token']))
        assert record.expires_at==absolute and record.created_at==created
    assert create('Після повторної перевірки').status_code==200
    assert create('CSRF не обходиться',{'X-CSRF-Token':'wrong'}).status_code==403


def test_embedded_reauth_changes_only_ui_and_still_requires_a_verified_session(prepared):
    from tests.test_mfa import enroll
    client,factory,uid,_=prepared
    assert client.get('/account/security?reauth=1').status_code==401
    assert client.get('/auth/mfa?reauth=1').status_code==401
    with factory() as db:
        token,_,_=enroll(db,uid);session=mfa.finish(db,token)
    client.cookies.set('project2_user',session['token']);headers={'X-CSRF-Token':session['csrf_token']}
    regular=client.get('/account/security');embedded=client.get('/account/security?reauth=1')
    assert 'id="app-sidebar"' in regular.text and 'id="app-sidebar"' not in embedded.text
    assert 'data-embedded-reauth="1"' in embedded.text
    assert client.post('/account/security/reauth',json={'password':PASSWORD},headers={'X-CSRF-Token':'wrong'}).status_code==403
    assert client.post('/account/security/reauth',json={'password':PASSWORD},headers=headers).status_code==200
    page=client.get('/auth/mfa?reauth=1');assert page.status_code==200
    assert 'data-embedded-reauth="1"' in page.text and 'id="app-sidebar"' not in page.text
    assert client.post('/auth/mfa/finish',json={},headers=headers).status_code==403

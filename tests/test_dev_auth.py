"""Legacy local bypass flags cannot replace a personal session."""
import pytest
from fastapi.testclient import TestClient
from tests.test_application_security import secure

@pytest.mark.parametrize('switch',['PROJECT2_DEV_AUTH_BYPASS','PROJECT2_DEV_ADMIN_OPEN'])
@pytest.mark.parametrize('peer',['127.0.0.1','::1','192.168.1.2'])
def test_legacy_bypass_flags_are_inert(secure,monkeypatch,switch,peer):
    client,*_=secure
    monkeypatch.setenv(switch,'1');monkeypatch.setenv('PROJECT2_AUTH_ALLOW_LOCAL_HTTP','1')
    with TestClient(client.app,base_url='http://localhost',client=(peer,1234)) as anonymous:
        assert anonymous.get('/auth/me').status_code in (401,403)
        assert anonymous.get('/admin').status_code in (401,403)

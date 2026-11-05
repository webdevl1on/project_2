"""Historical open-access switches now fail closed; no anonymous actor creation."""
import pytest
from tests.test_application_security import secure
from sqlalchemy import select,func
from app.models import User

@pytest.mark.parametrize('flag',[None,'0','1'])
def test_old_open_mode_never_exposes_subject_data(secure,monkeypatch,flag):
    client,factory,_,pid=secure
    if flag is None:monkeypatch.delenv('PROJECT2_AUTH_ENABLED',raising=False)
    else:monkeypatch.setenv('PROJECT2_AUTH_ENABLED',flag)
    for path in ['/persons','/admin',f'/persons/{pid}/medical',f'/persons/{pid}/documents']:
        assert client.get(path).status_code==401
    with factory() as db:assert db.scalar(select(func.count()).select_from(User))==3

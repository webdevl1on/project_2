"""Actual PostgreSQL: whole-route denial and real personal-session regression."""
from fastapi.testclient import TestClient
from app.main import app
from app.database.db import get_db
from app.models import Person
from app.services import accounts
from tests.test_application_security import routes
import re


def test_postgresql_all_registered_routes_fail_closed_and_real_roles_work(pg_factory):
    with pg_factory() as db:
        admin=accounts.create_user(db,'security-admin','Адміністратор PostgreSQL','synthetic-password','admin')
        accounts.create_user(db,'security-editor','Редактор PostgreSQL','synthetic-password','editor',actor_id=admin)
        person=Person();db.add(person);db.commit();pid=person.person_id
    def override():
        with pg_factory() as db:yield db
    previous=dict(app.dependency_overrides);app.dependency_overrides[get_db]=override
    try:
        with TestClient(app,base_url='https://testserver') as client:
            for method,path in routes():
                path=re.sub(r'\{[^}]+\}','1',path)
                response=client.request(method,path,json={} if method not in ('GET','HEAD') else None,follow_redirects=False)
                assert response.status_code==401,(method,path,response.text)
            response=client.post('/auth/login',json={'username':'security-editor','password':'synthetic-password'})
            assert response.status_code==200
            csrf=response.json()['csrf_token']
            for path in ['/persons','/person-positions','/staff/history','/events']:
                assert client.get(path).status_code==200,path
            assert client.get('/admin').status_code==403
            assert client.post(f'/persons/{pid}/personal-number',data={'personal_number':'test'}).status_code==403
            assert client.post(f'/persons/{pid}/personal-number',data={'personal_number':'test','csrf':csrf}).status_code==200
            assert client.post('/auth/logout',headers={'X-CSRF-Token':csrf}).status_code==200
            assert client.get('/persons').status_code==401
    finally:app.dependency_overrides.clear();app.dependency_overrides.update(previous)

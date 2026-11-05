"""Explicit regression client: real synthetic user, login cookie and CSRF.

Never imported by app/. Requires a test DB dependency override; no runtime bypass.
"""
import os
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.database.db import get_db
from app.models import User
from app.services import accounts


class AuthenticatedClient(TestClient):
    def __init__(self,app,*args,**kwargs):
        if os.environ.get('PROJECT2_ENV')!='testing' or get_db not in app.dependency_overrides:
            raise RuntimeError('AuthenticatedClient requires an explicitly isolated test DB override.')
        kwargs.setdefault('base_url','https://testserver')
        super().__init__(app,*args,**kwargs)
        dependency=app.dependency_overrides[get_db]()
        db=next(dependency)
        try:
            url=db.get_bind().url
            if url.get_backend_name()=='postgresql' and url.database!='project2_ci':raise RuntimeError('Refusing auth fixture outside project2_ci.')
            user=db.scalar(select(User).where(User.username=='regression-client'))
            if user is None:
                from sqlalchemy.dialects.postgresql import insert as pg_insert
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                insert=pg_insert if url.get_backend_name()=='postgresql' else sqlite_insert
                db.execute(insert(User).values(username='regression-client',display_name='Тестовий користувач регресії',role='admin',password_hash=accounts.password_hash('synthetic-regression-password')).on_conflict_do_nothing(index_elements=['username']));db.commit()
        finally:dependency.close()
        response=super().post('/auth/login',json={'username':'regression-client','password':'synthetic-regression-password'})
        if response.status_code!=200:raise AssertionError(response.text)
        self.headers['X-CSRF-Token']=response.json()['csrf_token']

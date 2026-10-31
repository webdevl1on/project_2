"""Explicit loopback development identity; never initialized by an HTTP request."""
import argparse
import hashlib
import hmac
import os
from pathlib import Path
import re
import secrets
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.transactions import service_transaction
from app.repositories.account_repository import AccountRepository as Repo
from app.models.accounts import User

USERNAME='project2-dev-local'
DISPLAY_NAME='Локальна розробка (тестовий автор)'
PREFIX='dev-only$'


def database_path(value=None):
    raw=value or os.environ.get('PROJECT2_DEV_AUTH_DATABASE')
    if not raw:raise ValueError('Вкажіть PROJECT2_DEV_AUTH_DATABASE — окрему тестову SQLite.')
    path=Path(raw).resolve()
    if path==Path('data/database/project2.db').resolve() or not re.search(r'(^|[_-])(test|testing|dev)([_\-.]|$)',path.name,re.I):
        raise ValueError('Потрібна окрема БД з test/dev у назві; project2.db заборонена.')
    if not path.is_file():raise ValueError('Тестова БД має вже існувати; автоматичного створення немає.')
    return path


def validate_user(user):
    if not user or not user.is_active or user.role!='editor' or user.display_name!=DISPLAY_NAME or not user.password_hash.startswith(PREFIX):
        raise ValueError('Ініціалізуйте тестового автора: python -m app.services.dev_auth --database PATH. Наявні облікові записи автоматично не змінюються.')
    return user


def identity(db):
    path=database_path()
    bound=db.get_bind().url.database
    if not bound or Path(bound).resolve()!=path:raise ValueError('Сесія не підключена до обраної тестової БД; обхід заборонено.')
    return validate_user(Repo.by_name(db,USERNAME))


def csrf(user):
    return hmac.new(user.password_hash.encode(),('dev-csrf:'+str(database_path())).encode(),hashlib.sha256).hexdigest()


def initialize(db):
    if os.environ.get('PROJECT2_DEV_AUTH_BYPASS')!='1':raise ValueError('Спочатку явно увімкніть PROJECT2_DEV_AUTH_BYPASS=1.')
    path=database_path()
    if not db.get_bind().url.database or Path(db.get_bind().url.database).resolve()!=path:raise ValueError('Неправильна тестова БД.')
    with service_transaction(db,immediate=True):
        user=Repo.by_name(db,USERNAME)
        if user:validate_user(user)
        else:
            user=Repo.add(db,User(username=USERNAME,display_name=DISPLAY_NAME,password_hash=PREFIX+secrets.token_hex(32),role='editor',is_active=True))
            db.flush()
        key=user.id
    return key


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--database',required=True)
    args=parser.parse_args(argv)
    engine=None
    try:
        if os.environ.get('PROJECT2_DEV_AUTH_BYPASS')!='1':raise ValueError('Потрібен PROJECT2_DEV_AUTH_BYPASS=1.')
        path=database_path(args.database)
        if path!=database_path():raise ValueError('--database має збігатися з PROJECT2_DEV_AUTH_DATABASE.')
        engine=create_engine('sqlite:///'+str(path))
        from app.database.schema_check import require_current_schema
        require_current_schema(engine)
        with Session(engine) as db:key=initialize(db)
    except (ValueError,OSError) as error:parser.error(str(error))
    finally:
        if engine:engine.dispose()
    print(f'Тестовий автор готовий, id={key}.')

if __name__=='__main__':main()

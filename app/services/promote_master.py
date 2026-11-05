"""Explicit, password-verified promotion of one existing personal Admin by ID."""
import argparse
from getpass import getpass
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.database.settings import Settings
from app.database.schema_check import require_current_schema


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user-id',type=int,required=True,help='Existing personal administrator ID, never inferred from a name')
    args=parser.parse_args(argv)
    try:settings=Settings.read()
    except ValueError as error:parser.error(str(error))
    from app.services import accounts
    engine=create_engine(settings.url,**settings.engine_options())
    try:
        require_current_schema(engine)
        with Session(engine) as db:
            user=accounts.promotion_target(db,args.user_id)
            revision=user.revision
            print(f'ID={user.id}; username={user.username}; display_name={user.display_name}; role={user.role}; активний={user.is_active}')
            print('Будуть збережені ID, логін, ім’я, пароль та історія. Зміниться роль; буде створено аудит.')
            password=getpass('Поточний пароль цього Admin: ')
            if input(f'Для підтвердження введіть MASTER {args.user_id}: ').strip()!=f'MASTER {args.user_id}':
                raise ValueError('Операцію скасовано. Змін немає.')
            accounts.promote_master(db,args.user_id,password,confirmed=True,expected_revision=revision)
            print('Master призначено. Якщо окремого активного Admin ще немає, створіть його через /admin/users.')
    except (ValueError,PermissionError) as error:parser.error(str(error))
    except SQLAlchemyError:parser.error('Зміни відхилено через конфлікт або помилку БД; операція відкотилася.')
    finally:engine.dispose()


if __name__=='__main__':main()

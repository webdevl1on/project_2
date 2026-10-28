"""Explicit first administrator, against an already migrated database."""
import argparse
from getpass import getpass
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.database.schema_check import require_current_schema
from app.services.accounts import create_user


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    parser.add_argument('--username', required=True); parser.add_argument('--display-name', required=True)
    args = parser.parse_args()
    if not args.database.is_file(): parser.error('Потрібна наявна мігрована SQLite.')
    password = getpass('Пароль (12–128 символів): ')
    if password != getpass('Повторіть пароль: '): parser.error('Паролі не збігаються.')
    engine = create_engine('sqlite:///'+str(args.database.resolve()))
    try:
        require_current_schema(engine)
        with Session(engine) as db: create_user(db, args.username, args.display_name, password, 'admin')
    except (ValueError, PermissionError) as error: parser.error(str(error))
    finally: engine.dispose()
    print('Першого адміністратора створено.')


if __name__ == '__main__': main()

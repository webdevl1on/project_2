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
    parser.add_argument('--database', type=Path,help='Only for explicit legacy SQLite; PostgreSQL uses DATABASE_URL')
    parser.add_argument('--username', required=True); parser.add_argument('--display-name', required=True)
    parser.add_argument('--allow-legacy-technical-accounts',action='store_true',help='Explicit first personal admin when only unchanged legacy technical accounts exist; preserves all records.')
    args = parser.parse_args()
    if args.database and not args.database.is_file():parser.error('Потрібна наявна мігрована SQLite.')
    password = getpass('Пароль (12–128 символів): ')
    if password != getpass('Повторіть пароль: '): parser.error('Паролі не збігаються.')
    if args.database:engine=create_engine('sqlite:///'+str(args.database.resolve()))
    else:
        from app.database.settings import Settings
        settings=Settings.read();engine=create_engine(settings.url,**settings.engine_options())
    try:
        require_current_schema(engine)
        with Session(engine) as db: create_user(db, args.username, args.display_name, password, 'admin',allow_legacy_bootstrap=args.allow_legacy_technical_accounts)
    except (ValueError, PermissionError) as error: parser.error(str(error))
    finally: engine.dispose()
    print('Першого адміністратора створено.')


if __name__ == '__main__': main()

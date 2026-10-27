"""Safely prepare a complete test database; importing this module changes nothing."""
import argparse
from pathlib import Path
import sys
import json
import sqlite3
from app.config import ROOT_DIR, EXCEL_PATH


def main(argv=None, *, confirm=input):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path)
    parser.add_argument('--excel',type=Path,default=EXCEL_PATH)
    parser.add_argument('--names',type=Path,default=ROOT_DIR/'reference_data/ukrainian_declension')
    parser.add_argument('--geography',type=Path,default=ROOT_DIR/'reference_data/geography')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--yes',action='store_true')
    args=parser.parse_args(argv)
    target=(args.database or ROOT_DIR/'data/database/project2.db').absolute()
    if args.yes and (args.database is None or 'test' not in target.stem.casefold() or target.resolve()==(ROOT_DIR/'data/database/project2.db').resolve()):
        parser.error('--yes дозволено лише з явним --database, назва якого містить test і не є основною БД.')
    try:
        from app.services.seed_bootstrap import preflight, populate
        from app.services.database_reset import check_target, check_space, reset_database
        from sqlalchemy.exc import SQLAlchemyError
        print('Preflight: файли, контрольні суми, заголовки, дублікати, FK та конфігурація…')
        check_target(target)
        prepared=preflight(args.excel,args.names,args.geography)
        # Includes staging, target backup and index overhead; no whole street ORM session.
        source_size=sum(path.stat().st_size for path in args.geography.glob('*.csv'))
        required_space=max(256*1024**2,source_size*6)+(target.stat().st_size if target.exists() else 0)
        check_space(target,required_space)
        print(f'БД: {target}')
        print(f'Preflight OK: ПІБ {prepared["names"]["count"]}; географія {prepared["geography"]["counts"]}; посади {prepared["positions"]}; люди {prepared["people"]}.')
        print('CSV checksum: враховано нормалізацію Git LF / вихідний CSV CRLF; інші розбіжності заборонено.')
        print('Виключено: manual_review.xlsx, streets_unresolved.csv, hierarchy_issues.csv, countries_excluded.csv та Excel-дублікати географії.')
        if args.dry_run:
            print('Dry-run завершено; БД не створювалася й не змінювалася.'); return 0
        if not args.yes:
            print('УВАГА: поточні дані цієї БД будуть замінені тестовими. Зупиніть сервер. Буде створено backup.')
            if confirm('Введіть RESET: ')!='RESET': print('Скасовано; БД не змінено.'); return 1
        report,backup=reset_database(target,lambda path:populate(path,args.excel,args.names,args.geography,prepared),required_space=required_space)
        print('Готово. '+json.dumps(report,ensure_ascii=False))
        print(f'Backup: {backup}' if backup else 'Попередньої БД не було; backup не потрібний.')
        return 0
    except (OSError,ValueError,EOFError,sqlite3.Error) as error:
        print(f'Reset скасовано: {error}',file=sys.stderr); return 2
    except SQLAlchemyError:
        print('Reset скасовано через помилку БД; staging відкинуто, стара БД збережена. SQL/персональні значення не виводяться.',file=sys.stderr); return 2



if __name__=='__main__':
    raise SystemExit(main())

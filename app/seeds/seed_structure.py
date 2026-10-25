from app.seeds.seed_event_types import seed_event_types
from app.seeds.seed_event_subtypes import seed_event_subtypes
from app.seeds.seed_reference import seed_ranks
from app.config import EXCEL_PATH
from app.seeds.seed_reference import seed_positions

def seed_all_structure(db, excel_path=EXCEL_PATH, *, version_name=None, valid_from=None, valid_to=None, structure_code="main"):

    seed_event_types(db)
    db.flush()

    seed_event_subtypes(db)

    seed_ranks(db)

    if version_name:
        if valid_from is None: raise ValueError("Вкажіть точну дату початку версії.")
        seed_positions(db, excel_path, version_name=version_name, valid_from=valid_from, valid_to=valid_to, structure_code=structure_code)

    print("=== COMMIT ===")
    db.commit()
    print("=== COMMIT DONE ===")


def main(argv=None):
    import argparse
    from pathlib import Path
    import sys
    from sqlalchemy import URL, create_engine
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import sessionmaker
    from app.database.db import DB_PATH
    from app.database.schema_check import require_current_schema

    parser = argparse.ArgumentParser(description="Окреме засівання довідників без створення або очищення БД.")
    parser.add_argument("--database", type=Path, default=DB_PATH)
    parser.add_argument("--excel", type=Path, default=EXCEL_PATH)
    from datetime import date
    parser.add_argument("--version-name")
    parser.add_argument("--valid-from", type=date.fromisoformat)
    parser.add_argument("--valid-to", type=date.fromisoformat)
    parser.add_argument("--structure-code", default="main")
    args = parser.parse_args(argv)
    if bool(args.version_name) != bool(args.valid_from):
        parser.error("--version-name та --valid-from потрібно вказати разом")
    if not args.database.is_file():
        print("Помилка: файл SQLite не існує; спочатку створіть поточну схему.", file=sys.stderr)
        return 2
    selected_engine = create_engine(URL.create("sqlite", database=str(args.database.resolve())))
    try:
        require_current_schema(selected_engine)
        with sessionmaker(bind=selected_engine, autoflush=False)() as db:
            try:
                seed_all_structure(db, args.excel, version_name=args.version_name, valid_from=args.valid_from, valid_to=args.valid_to, structure_code=args.structure_code)
            except Exception:
                db.rollback()
                raise
    except SQLAlchemyError:
        print("Помилка БД: перевірте поточну схему та цілісність; засівання довідників скасовано.", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"Помилка: {error}", file=sys.stderr)
        return 2
    except (OSError, KeyError) as error:
        print(f"Помилка довідника Excel: {type(error).__name__}; засівання скасовано.", file=sys.stderr)
        return 2
    finally:
        selected_engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

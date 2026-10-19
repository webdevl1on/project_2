import argparse
from pathlib import Path
import sys

from sqlalchemy import URL, create_engine

from app.database.db import engine, DB_PATH
from app.database.base import Base
import app.models  # Registers all models in Base.metadata.

def init_db(bind=None):
    Base.metadata.create_all(bind=bind if bind is not None else engine)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Створити поточну схему SQLite у вибраному файлі.")
    parser.add_argument("--database", type=Path, help="Явний шлях до SQLite; типовий — data/database/project2.db")
    parser.add_argument("--recreate", action="store_true", help="Явно дозволити видалення вибраної SQLite та створення нової")
    args = parser.parse_args(argv)
    if args.recreate and args.database is None:
        parser.error("--recreate вимагає явного --database; автоматичне видалення типової БД заборонено")
    path = (args.database or DB_PATH).resolve()
    try:
        if path.exists():
            if not args.recreate:
                raise ValueError("Файл уже існує; без --recreate його не змінено.")
            if not path.is_file():
                raise ValueError("Вибраний шлях не є файлом SQLite.")
            with path.open("rb") as source:
                header = source.read(16)
            if header and header != b"SQLite format 3\x00":
                raise ValueError("Вибраний файл не є SQLite; видалення заборонено.")
            if any(Path(str(path) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
                raise ValueError("Є службові SQLite-файли; спочатку коректно закрийте сервер і всі підключення до цієї БД.")
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation also protects against replacing a concurrently created file.
        with path.open("xb"):
            pass
        selected_engine = create_engine(URL.create("sqlite", database=str(path)))
        try:
            init_db(selected_engine)
        finally:
            selected_engine.dispose()
    except (OSError, ValueError) as error:
        print(f"Помилка: {error}", file=sys.stderr)
        return 2
    print(f"Створено схему SQLite: {path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

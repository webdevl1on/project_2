"""Read-only check: create_all cannot upgrade an existing SQLite schema."""

from sqlalchemy import inspect

from app.database.base import Base


def require_current_schema(engine):
    from app import models  # Register all current tables before inspection.

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing = []
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:
            missing.append(table.name)
            continue
        columns = {column["name"] for column in inspector.get_columns(table.name)}
        missing.extend(f"{table.name}.{column.name}" for column in table.columns if column.name not in columns)
    if missing:
        raise ValueError("Схема SQLite застаріла або неповна. Відсутні: " + ", ".join(missing)
                         + ". Підготуйте нову базу або явно пересоздайте тестову; автоматичного оновлення немає.")

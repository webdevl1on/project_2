"""Read-only verification of Alembic and PostgreSQL-specific integrity objects."""
from pathlib import Path
import re
from sqlalchemy import inspect,text

REVISION='0003_event_corrections'


def require_postgresql_schema(engine):
    from app.database.base import Base
    from app import models
    inspector=inspect(engine)
    tables=set(inspector.get_table_names())
    if 'alembic_version' not in tables:raise ValueError('Виконайте alembic upgrade head; автоматичної міграції немає.')
    missing=[]
    for table in Base.metadata.sorted_tables:
        if table.name not in tables:missing.append(table.name);continue
        actual={c['name'] for c in inspector.get_columns(table.name)}
        missing.extend(table.name+'.'+c.name for c in table.columns if c.name not in actual)
    root=Path(__file__).resolve().parents[2]/'migrations/sql'
    guard_sql=(root/'initial_guards.sql').read_text()
    expected_triggers=set(re.findall(r'CREATE TRIGGER (\w+)',guard_sql)) | {'event_correction_no_update','event_correction_no_delete','person_event_no_delete','person_event_annulled_immutable'}
    expected_constraints=set(re.findall(r'ALTER TABLE (\w+) ADD CONSTRAINT (\w+)',guard_sql))
    with engine.connect() as db:
        if set(db.scalars(text('SELECT version_num FROM alembic_version')))!={REVISION}:missing.append('Alembic revision')
        triggers=set(db.scalars(text("SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema() AND NOT t.tgisinternal AND t.tgenabled!='D'")))
        missing.extend('trigger:'+name for name in expected_triggers-triggers)
        constraints=set(db.execute(text("SELECT c.relname,k.conname FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema()")))
        missing.extend('constraint:'+table+'.'+name for table,name in expected_constraints-constraints)
        functions=set(db.scalars(text('SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=current_schema()')))
        missing.extend('function:'+name for name in {'project2_components','project2_strip','project2_norm','project2_typed','unicode_contains','formatted_address','project2_date_match'}-functions)
        for table in Base.metadata.sorted_tables:
            for index in table.indexes:
                if index.dialect_options['postgresql']['where'] is not None:
                    predicate=db.scalar(text('SELECT pg_get_expr(i.indpred,i.indrelid) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.relname=:name AND n.nspname=current_schema()'),{'name':index.name})
                    if not predicate:missing.append('partial index:'+index.name)
    if missing:raise ValueError('PostgreSQL схема неповна: '+', '.join(sorted(missing)))

from alembic import context
from sqlalchemy import create_engine
from app.database.settings import Settings
from app.database.base import Base
from app import models
config=context.config
settings=Settings.read()
if settings.url.drivername!='postgresql+psycopg':raise ValueError('Alembic призначений тільки для PostgreSQL.')
if context.is_offline_mode():
    context.configure(url=settings.url,target_metadata=Base.metadata,literal_binds=True)
    with context.begin_transaction():context.run_migrations()
else:
    engine=create_engine(settings.url,**settings.engine_options())
    from contextlib import nullcontext
    provided=config.attributes.get('connection')
    with (nullcontext(provided) if provided is not None else engine.connect()) as connection:
        context.configure(connection=connection,target_metadata=Base.metadata,compare_type=True)
        with context.begin_transaction():context.run_migrations()
    engine.dispose()

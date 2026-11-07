"""Cross-process lease: a running web server and a reset cannot overlap."""
from contextlib import contextmanager
from pathlib import Path
import os


@contextmanager
def database_lease(database, *, shared=False):
    path=Path(str(Path(database).resolve())+'.maintenance.lock')
    path.parent.mkdir(parents=True,exist_ok=True)
    stream=path.open('a+b')
    try:
        if os.name=='nt':
            import msvcrt
            stream.seek(0)
            if not stream.read(1): stream.write(b'0'); stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBRLCK if shared else msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream, (fcntl.LOCK_SH if shared else fcntl.LOCK_EX)|fcntl.LOCK_NB)
    except OSError:
        stream.close()
        raise ValueError('БД використовується сервером або іншим reset; спочатку зупиніть їх.') from None
    try: yield
    finally:
        if os.name=='nt':
            import msvcrt
            stream.seek(0); msvcrt.locking(stream.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(stream,fcntl.LOCK_UN)
        stream.close()


async def application_lifespan(app):
    from app.database.db import engine, DB_PATH, settings
    if app.dependency_overrides:  # Test ASGI applications own their isolated schema/session.
        yield
        return
    from app.database.schema_check import require_current_schema
    try:
        if engine.dialect.name=='postgresql':
            require_current_schema(engine)
            from sqlalchemy.orm import Session
            from app.security.mfa_config import require_keys,relying_party
            with Session(engine) as db:require_keys(db)
            relying_party()
            yield
        else:
            with database_lease(DB_PATH,shared=True):
                require_current_schema(engine)
                from sqlalchemy.orm import Session
                from app.security.mfa_config import require_keys,relying_party
                with Session(engine) as db:require_keys(db)
                relying_party()
                yield
    finally:engine.dispose()

from contextlib import asynccontextmanager
application_lifespan=asynccontextmanager(application_lifespan)

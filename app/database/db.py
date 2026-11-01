from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.base import Base
from app.database.settings import Settings

settings=Settings.read()
import os
for name,key in {'documents':'PROJECT2_DOCUMENT_STORAGE','photos':'PROJECT2_PHOTO_STORAGE','temporary':'PROJECT2_TEMP_STORAGE','exports':'PROJECT2_EXPORT_STORAGE','backups':'PROJECT2_BACKUP_STORAGE'}.items():
    os.environ.setdefault(key,str(settings.paths[name]))
DB_PATH=Path(settings.url.database) if settings.url.drivername=='sqlite' else None
engine=create_engine(settings.url,**settings.engine_options())
SessionLocal=sessionmaker(autocommit=False,autoflush=False,bind=engine)


def get_db():
    db=SessionLocal()
    try:yield db
    except Exception:
        db.rollback();raise
    finally:db.close()

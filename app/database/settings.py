"""Explicit environment/connection policy. Never fall back to a working SQLite."""
from dataclasses import dataclass
from pathlib import Path
import os
from sqlalchemy.engine import make_url
from dotenv import load_dotenv

load_dotenv(os.environ.get('PROJECT2_ENV_FILE','.env'),override=False)

@dataclass(frozen=True)
class Settings:
    environment: str
    url: object
    paths: dict

    @classmethod
    def read(cls):
        mode=os.environ.get('PROJECT2_ENV')
        if mode not in ('development','testing','production'):raise ValueError('Задайте PROJECT2_ENV=development|testing|production.')
        raw=os.environ.get('DATABASE_URL')
        if not raw:raise ValueError('DATABASE_URL обов’язковий; автоматичного SQLite fallback немає.')
        try:url=make_url(raw)
        except Exception:raise ValueError('Некоректний DATABASE_URL.') from None
        if url.drivername not in ('postgresql+psycopg','sqlite'):raise ValueError('Потрібен postgresql+psycopg або явна legacy SQLite.')
        if mode=='testing' and url.drivername.startswith('postgresql') and url.database!='project2_ci':raise ValueError('PostgreSQL тести дозволені лише у project2_ci.')
        if mode=='development' and url.drivername.startswith('postgresql') and url.database!='project2_dev':raise ValueError('Development потребує окремої project2_dev.')
        if mode=='production':
            if url.database!='project2_prod':raise ValueError('Production потребує project2_prod з окремим обліковим записом.')
            if not url.drivername.startswith('postgresql') or not url.host or not url.database or not url.username:raise ValueError('Production потребує явного PostgreSQL-підключення.')
            if len(os.environ.get('STAFF_SIGNING_KEY',''))<32:raise ValueError('Production потребує стабільного STAFF_SIGNING_KEY (32+ символів).')
            if os.environ.get('PROJECT2_AUTH_ENABLED')!='1' or any(os.environ.get(k)=='1' for k in ('PROJECT2_DEV_AUTH_BYPASS','PROJECT2_DEV_ADMIN_OPEN')):raise ValueError('Production забороняє вимкнену авторизацію та dev bypass.')
        keys={'documents':'PROJECT2_DOCUMENT_STORAGE','photos':'PROJECT2_PHOTO_STORAGE','temporary':'PROJECT2_TEMP_STORAGE','exports':'PROJECT2_EXPORT_STORAGE','backups':'PROJECT2_BACKUP_STORAGE'}
        if mode=='production' and any(not os.environ.get(k) for k in keys.values()):raise ValueError('Production потребує всіх окремих файлових каталогів.')
        paths={name:Path(os.environ.get(key,f'data/{mode}/{name}')).resolve() for name,key in keys.items()}
        if len(set(paths.values()))!=len(paths) or any(a in b.parents for a in paths.values() for b in paths.values() if a!=b):raise ValueError('Каталоги сховищ повинні бути незалежними.')
        return cls(mode,url,paths)

    def engine_options(self):
        if self.url.drivername=='sqlite':return {'echo':False,'hide_parameters':True}
        return {'hide_parameters':True,'pool_pre_ping':True,'pool_size':int(os.environ.get('PROJECT2_POOL_SIZE','5')),'max_overflow':int(os.environ.get('PROJECT2_MAX_OVERFLOW','5')),'pool_timeout':int(os.environ.get('PROJECT2_POOL_TIMEOUT','20')),'connect_args':{'connect_timeout':10,'options':'-c timezone=UTC -c lock_timeout=10000 -c statement_timeout=120000'}}

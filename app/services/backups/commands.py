"""Authenticated application use cases; privileged file/restore work stays in the worker/CLI."""
from app.services import accounts
from app.services.access_management import fresh
from app.database.db import settings
from .config import BackupConfig
from .engine import BackupEngine


def authorize(db,user_id,*,critical=False):
    user=accounts.authorize(db,user_id,('master',) if critical else ('master','admin'))
    if critical:fresh(db,user)
    return user

def backend(db):return BackupEngine(db.get_bind(),settings,BackupConfig.load(settings))

def status(db,user_id):
    user=authorize(db,user_id)
    try:
        engine=backend(db);result=engine.store.status()
        # OS paths, encrypted manifest contents and key identifiers are never returned by HTTP.
        result['can_run']=user.role=='master';return result
    except (ValueError,TypeError,KeyError,OSError):return {'configured':False,'can_run':False,'backups':[],'jobs':[],'events':[],'message':'Налаштуйте захищений worker, ключі та конфігурацію резервування на сервері.'}

def enqueue(db,user_id,operation,identity=None):
    user=authorize(db,user_id,critical=True);engine=backend(db)
    engine.initialize()
    if operation=='verify':engine.store.read('catalog',identity)
    return engine.store.enqueue(operation,user.id,identity)

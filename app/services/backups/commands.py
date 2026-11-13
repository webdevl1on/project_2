"""Authenticated application use cases; privileged file/restore work stays in the worker/CLI."""
from app.services import accounts
from app.services.access_management import fresh
from app.database.db import settings
from .config import BackupConfig
from .engine import BackupEngine


def authorize(db,user_id,*,critical=False):
    user=accounts.authorize(db,user_id,('master','admin'))
    if critical:fresh(db,user)
    return user

def backend(db):return BackupEngine(db.get_bind(),settings,BackupConfig.load(settings))

def status(db,user_id):
    user=authorize(db,user_id)
    try:
        engine=backend(db);result=engine.store.status()
        # OS paths, encrypted manifest contents and key identifiers are never returned by HTTP.
        result['can_run']=True
        statistics=engine.store.records('statistics');result['statistics']=max(statistics,key=lambda r:r['at']) if statistics else None
        emergency=engine.store.records('emergency');last=max(emergency,key=lambda r:r['at']) if emergency else None
        result['emergency']=({k:last[k] for k in ('id','at','day')} if last else None)
        result['can_export']=False
        if engine.config.emergency_root:
            try:
                from .emergency import authorize_export
                authorize_export(db,user.id);result['can_export']=True
            except PermissionError:pass
        return result
    except (ValueError,TypeError,KeyError,OSError):return {'configured':False,'can_run':False,'backups':[],'jobs':[],'events':[],'message':'Налаштуйте захищений worker, ключі та конфігурацію резервування на сервері.'}

def enqueue(db,user_id,operation,identity=None,*,details=None):
    user=authorize(db,user_id,critical=True);engine=backend(db)
    engine.initialize()
    if operation not in ('create','verify','emergency','usb','statistics'):raise ValueError('BACKUP_OPERATION_INVALID')
    if operation=='verify':engine.store.read('catalog',identity)
    data={}
    if operation in ('emergency','usb'):
        from .emergency import authorize_export
        authorize_export(db,user.id)
        if not engine.config.emergency_root:raise ValueError('EMERGENCY_ROOT_REQUIRED')
    if operation=='usb':
        from .windows_storage import check_request
        if not isinstance(details,dict) or set(details)!={'volume_id'} or not isinstance(details['volume_id'],str):raise ValueError('USB_VOLUME_ID_INVALID')
        check_request(engine,details['volume_id']);data=details
    return engine.store.enqueue(operation,user.id,identity,details=data)

def volumes(db,user_id):
    user=authorize(db,user_id)
    from .emergency import authorize_export
    from .usb import available
    authorize_export(db,user.id);return available(backend(db))

"""Authenticated application use cases; privileged file/restore work stays in the worker/CLI."""
from datetime import datetime

from app.services import accounts
from app.services.access_management import fresh
from app.database.db import settings
from .config import BackupConfig
from .engine import BackupEngine
from .store import stamp
from .status_view import (ACTIVE_STATES, last_usb, public_backup, public_emergency, public_event,
                          public_job, public_statistics, with_kyiv)


def authorize(db,user_id,*,critical=False):
    user=accounts.authorize(db,user_id,('master','admin'))
    if critical:fresh(db,user)
    return user

def backend(db):return BackupEngine(db.get_bind(),settings,BackupConfig.load(settings))

def status(db,user_id,*,watched_ids=()):
    user=authorize(db,user_id)
    try:
        engine=backend(db);result=engine.store.status()
        # Keep durable records private. The HTTP contract contains display metadata only.
        jobs = sorted(result['jobs'], key=lambda job: datetime.fromisoformat(job['at']), reverse=True)
        events = result['events']
        versions = {row['id']: row for row in engine.store.records('emergency') if row.get('ready')}
        latest = max(versions.values(), key=lambda row: datetime.fromisoformat(row['at']), default=None)
        statistics = max(engine.store.records('statistics'), key=lambda row: row['at'], default=None)
        result.update(can_run=True, server_at=stamp(), statistics=public_statistics(statistics),
                      emergency=public_emergency(latest), last_usb=last_usb(engine, jobs, events, versions, latest),
                      last_full=next((public_backup(row) for row in result['backups']
                                      if row['kind'] == 'full' and row['integrity'] == 'VERIFIED'), None),
                      backups=[public_backup(row) for row in result['backups']],
                      jobs=[public_job(job) for job in jobs[:5]],
                      watched_jobs=[public_job(job) for job in jobs if job['id'] in watched_ids],
                      active_jobs=[public_job(job) for job in jobs if job['state'] in ACTIVE_STATES],
                      events=[public_event(event) for event in events])
        for key in ('last_success', 'last_integrity'):
            result[key] = public_backup(result[key])
        for key in ('last_failure', 'last_drill'):
            result[key] = public_event(result[key])
        with_kyiv(result, 'next_at')
        result['can_export']=False
        if engine.config.emergency_root:
            try:
                from .emergency import authorize_export
                authorize_export(db,user.id);result['can_export']=True
            except PermissionError:pass
        return result
    except (ValueError,TypeError,KeyError,OSError):return {'configured':False,'can_run':False,'backups':[],'jobs':[],'active_jobs':[],'events':[],'last_full':None,'emergency':None,'last_usb':None,'message':'Налаштуйте захищений worker, ключі та конфігурацію резервування на сервері.'}

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

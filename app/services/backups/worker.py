"""Durable serial maintenance jobs: one retry, no permanent-artifact deletion."""
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from sqlalchemy.orm import Session
from app.models import User
from .store import now,stamp


def enqueue_due(backup):
    store=backup.store;at=now();events=store.events()
    clock=backup.config.root/'schedule-start.json'
    if not clock.exists():backup.ring.save(clock,{'at':at.isoformat()})
    started=datetime.fromisoformat(backup.ring.read(clock)['at'])
    # Stable time slots are remembered even after two failed attempts or a restart.
    slot=at.replace(minute=(at.minute//backup.config.interval_minutes)*backup.config.interval_minutes,second=0,microsecond=0)
    store.enqueue('create',None,details={'kind':'full','slot':slot.isoformat(),'schedule':'hourly'},scheduled=True)
    daily=at.replace(hour=backup.config.daily_hour,minute=0,second=0,microsecond=0)
    if at<daily:daily-=timedelta(days=1)
    if at.hour>=backup.config.daily_hour or daily>=started:
        store.enqueue('create',None,details={'kind':'full','slot':daily.date().isoformat(),'schedule':'daily'},scheduled=True)
    if backup.config.emergency_enabled:
        local=at.astimezone(ZoneInfo('Europe/Kyiv'))
        scheduled=local.replace(hour=backup.config.emergency_hour,minute=0,second=0,microsecond=0)
        if local<scheduled:scheduled-=timedelta(days=1)
        if local.hour>=backup.config.emergency_hour or scheduled>=started:
            store.enqueue('emergency',None,details={'slot':scheduled.date().isoformat()},scheduled=True)
    statistics=[e for e in events if e['operation']=='statistics' and e['result']=='SUCCESS']
    if not statistics or datetime.fromisoformat(statistics[-1]['at'])+timedelta(days=7)<=at:
        store.enqueue('statistics',None,details={'slot':at.date().isoformat()},scheduled=True)


def perform(backup,job):
    operation=job['operation'];actor=job['actor_user_id']
    if operation=='create':
        # A completed dump survives a failed drill/restart. Never replace it on retry.
        identity=job.get('backup_id');creation_error=None
        if not identity:
            matches=[r for r in backup.store.records('catalog') if r.get('job_id')==job['id'] and r['integrity']=='VERIFIED']
            if matches:identity=matches[-1]['id']
            else:
                try:result=backup.create(kind=job.get('details',{}).get('kind','full'),actor=actor,job_id=job['id'])
                except ValueError as error:
                    matches=[r for r in backup.store.records('catalog') if r.get('job_id')==job['id'] and r['integrity']=='VERIFIED']
                    if not matches:raise
                    result=matches[-1];creation_error=error
                result['schedule']=job.get('details',{}).get('schedule','manual');backup.store.save('catalog',result);identity=result['id']
            job['backup_id']=identity;backup.store.save('jobs',job)
        backup.verify(identity,actor=actor)
        from .drills import maybe_run
        result=maybe_run(backup,force=True,identity=identity,required=True,actor=actor)
        if result is None:raise ValueError('BACKUP_DRILL_APPROVAL_REQUIRED')
        if creation_error:raise creation_error
        if backup.config.external and backup.store.read('catalog',identity)['external']!='VERIFIED':backup.replicate(identity)
        return {'backup_id':identity}
    if operation=='verify':return backup.verify(job['backup_id'],actor=actor)
    if operation=='emergency':
        from .emergency import generate
        return generate(backup,actor=actor,job_id=job['id'])
    if operation=='usb':
        from .usb import export
        return export(backup,job['details']['volume_id'],actor=actor,job_id=job['id'])
    if operation=='statistics':
        from .statistics import collect
        return collect(backup,actor=actor)
    raise ValueError('BACKUP_OPERATION_INVALID')


def run_once(backup):
    backup.initialize()
    with backup.operation_lock():
        from .windows_storage import refresh_devices
        refresh_devices(backup)
        jobs=backup.store.records('jobs')
        for job in jobs:
            if job['state']=='RUNNING':
                job['state']='QUEUED' if job.get('attempts',1)<2 else 'FAILED'
                job['code']='BACKUP_WORKER_INTERRUPTED';backup.store.save('jobs',job)
                backup.store.event('worker',job['state'],actor=job['actor_user_id'],code=job['code'],details={'attempt':job.get('attempts',1)})
                if job['state']=='FAILED':backup.alert(job['code'],job.get('backup_id'))
        pending=next((j for j in sorted(jobs,key=lambda j:j['at']) if j['state']=='QUEUED'),None)
        if pending is None:
            enqueue_due(backup)
            pending=next((j for j in sorted(backup.store.records('jobs'),key=lambda j:j['at']) if j['state']=='QUEUED'),None)
        if pending is None:return True
        job=pending
        if job.get('attempts',0)>=2:return False
        job.update(state='RUNNING',attempts=job.get('attempts',0)+1);backup.store.save('jobs',job)
        try:
            if not job.get('scheduled'):
                with Session(backup.db_engine) as db:
                    user=db.get(User,job['actor_user_id']);allowed=user and user.is_active and user.role in ('master','admin')
                    if not allowed:raise ValueError('BACKUP_AUTHORIZATION_EXPIRED')
                    if not job.get('authorized_at') and (now()-datetime.fromisoformat(job['at'])).total_seconds()>300:raise ValueError('BACKUP_AUTHORIZATION_EXPIRED')
                    if job['operation'] in ('usb','emergency'):
                        from .emergency import authorize_export
                        authorize_export(db,user.id)
                job['authorized_at']=job.get('authorized_at') or stamp();backup.store.save('jobs',job)
            result=perform(backup,job);job.update(state='SUCCESS',result=result,completed_at=stamp())
            backup.store.event('job','SUCCESS',actor=job['actor_user_id'],identity=job.get('backup_id'),details={'attempt':job['attempts'],'operation':job['operation']})
        except Exception as error:
            code=str(error) if isinstance(error,ValueError) and str(error).startswith(('BACKUP_','EMERGENCY_','USB_','STORAGE_')) else 'BACKUP_JOB_FAILED'
            retry=job['attempts']<2 and code!='BACKUP_AUTHORIZATION_EXPIRED'
            job.update(state='QUEUED' if retry else 'FAILED',code=code)
            backup.store.event('retry' if retry else 'job','QUEUED' if retry else 'FAILED',actor=job['actor_user_id'],identity=job.get('backup_id'),code=code,details={'attempt':job['attempts'],'slot':job.get('details',{}).get('slot'),'operation':job['operation']})
            if not retry:backup.alert(code,job.get('backup_id'))
        backup.store.save('jobs',job)
        return job['state']=='SUCCESS'

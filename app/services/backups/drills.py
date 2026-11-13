"""Narrow Master-approved unattended drills, never restore/cutover of a working DB."""
from datetime import datetime,timedelta
from pathlib import Path
import os,tempfile,uuid
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.models import User
from .crypto import private_dir
from .store import now,stamp
from . import restore
from app.repositories.backup_repository import SSL_OPTIONS


def drill_url(variable):
    try:url=make_url(os.environ[variable])
    except (KeyError,ValueError):raise ValueError('BACKUP_DRILL_CONFIGURATION_REQUIRED') from None
    if url.drivername!='postgresql+psycopg' or url.database!='project2_ci' or set(url.query)-SSL_OPTIONS.keys():raise ValueError('BACKUP_DRILL_REQUIRES_ISOLATED_CI')
    return url


def approve(backup,actor,variable,reason,days,confirmed):
    if confirmed is not True or not isinstance(reason,str) or not reason.strip() or len(reason)>2000 or type(days) is not int or not 0<=days<=30 or not backup.config.drill_root:raise ValueError('BACKUP_DRILL_APPROVAL_REQUIRED')
    with Session(backup.db_engine) as db:
        master=db.get(User,actor)
        if not master or not master.is_active or master.role!='master':raise PermissionError('BACKUP_DRILL_MASTER_REQUIRED')
    url=drill_url(variable)
    permit={'actor_user_id':actor,'target':restore.fingerprint(url),'variable':variable,'expires_at':(now()+timedelta(days=days)).isoformat() if days else None,'active':True,'reason':reason.strip()}
    backup.ring.save(backup.config.root/'drill-permit.json',permit)
    backup.store.event('drill_approval','SUCCESS',actor=actor,details={'expires_at':permit['expires_at']})


def maybe_run(backup,*,force=False,identity=None,required=False,actor=None):
    permit_path=backup.config.root/'drill-permit.json'
    if not backup.config.drill_root or not permit_path.exists():
        if required:raise ValueError('BACKUP_DRILL_APPROVAL_REQUIRED')
        return None
    permit=backup.ring.read(permit_path)
    if not permit['active']:
        if required:raise ValueError('BACKUP_DRILL_APPROVAL_REQUIRED')
        return None
    if permit['expires_at'] and datetime.fromisoformat(permit['expires_at'])<=now():raise ValueError('BACKUP_DRILL_APPROVAL_EXPIRED')
    url=drill_url(permit['variable'])
    if backup.settings.environment!='testing' and (url.host,url.port or 5432)==(backup.db_engine.url.host,backup.db_engine.url.port or 5432):raise ValueError('BACKUP_DRILL_SEPARATE_CLUSTER_REQUIRED')
    if restore.fingerprint(url)!=permit['target']:raise ValueError('BACKUP_DRILL_TARGET_CHANGED')
    with Session(backup.db_engine) as db:
        master=db.get(User,permit['actor_user_id'])
        if not master or not master.is_active or master.role!='master':raise PermissionError('BACKUP_DRILL_MASTER_REQUIRED')
    events=backup.store.events();previous=[e for e in events if e['operation']=='drill' and e['result']=='SUCCESS']
    if not force and previous and datetime.fromisoformat(previous[-1]['at'])+timedelta(hours=backup.config.drill_hours)>now():return None
    good=[r for r in backup.store.records('catalog') if r['integrity']=='VERIFIED']
    if not good:return None
    identity=identity or max(good,key=lambda r:r['snapshot_at'])['id']
    if identity not in {r['id'] for r in good}:raise ValueError('BACKUP_DRILL_COPY_NOT_VERIFIED')
    database='project2_restore_'+uuid.uuid4().hex
    target=url.set(database=database);admin=create_engine(url,isolation_level='AUTOCOMMIT',hide_parameters=True);created=False
    private_dir(backup.config.drill_root)
    try:
        with admin.connect() as db:db.execute(text('CREATE DATABASE "'+database+'"'));created=True
        with tempfile.TemporaryDirectory(prefix='drill-',dir=backup.config.drill_root) as raw:
            with backup.store.server_events(master.id,actor):
                plan=restore.plan(backup,identity,target.render_as_string(hide_password=False),actor=master.id,reason='Затверджене регулярне випробування відновлення')
                result=restore.apply(backup,plan['id'],target.render_as_string(hide_password=False),Path(raw)/'recovered',actor=master.id,confirmed=True)
        record=backup.store.read('catalog',identity);record.update(drill='SUCCESS',drilled_at=stamp(),restore_seconds=result['restore_seconds']);backup.store.save('catalog',record)
        backup.store.event('drill','SUCCESS',identity=identity,details={'restore_seconds':result['restore_seconds'],'snapshot_at':result['snapshot_at'],'approved_by_user_id':master.id,'initiated_by_user_id':actor})
        return result
    except Exception:
        record=backup.store.read('catalog',identity);record.update(drill='FAILED');backup.store.save('catalog',record)
        backup.store.event('drill','FAILED',identity=identity,code='BACKUP_DRILL_FAILED',details={'approved_by_user_id':master.id,'initiated_by_user_id':actor});backup.alert('BACKUP_DRILL_FAILED',identity)
        raise ValueError('BACKUP_DRILL_FAILED') from None
    finally:
        if created:
            # Only this invocation's fresh random database, never a supplied name.
            with admin.connect() as db:db.execute(text('DROP DATABASE "'+database+'" WITH (FORCE)'))
        admin.dispose()

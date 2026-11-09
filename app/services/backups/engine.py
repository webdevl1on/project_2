"""One complete restore point: PostgreSQL snapshot + pinned files + separate secrets."""
from contextlib import contextmanager
from datetime import datetime,UTC,timedelta
from pathlib import Path
import json,os,shutil,tempfile,time,uuid,hashlib,subprocess
from sqlalchemy import text
from app.database.postgresql import require_postgresql_schema,REVISION
from app.database.maintenance import database_lease
from app.repositories.backup_repository import BackupRepository as Repo
from .crypto import Keyring,private_dir,private_file,sha,canonical
from .store import Store,stamp,key,now
from .bundle import inventory,pack,open_bundle,validate_refs,secrets_payload,check_mfa


def publish(source,destination):
    if destination.exists() or destination.is_symlink():raise ValueError('BACKUP_DESTINATION_EXISTS')
    temporary=destination.with_name('.'+destination.name+'.partial')
    created=False
    try:
        out=private_file(temporary);created=True
        with out,source.open('rb') as inp:shutil.copyfileobj(inp,out);out.flush();os.fsync(out.fileno())
        os.rename(temporary,destination)
    finally:
        if created:temporary.unlink(missing_ok=True)

class BackupEngine:
    def __init__(self,db_engine,settings,config):
        config.validate(settings.paths)
        self.db_engine=db_engine;self.settings=settings;self.config=config
        self.ring=Keyring(config.key_file);self.secret_ring=Keyring(config.secrets_key_file)
        if set(self.ring.keys.values())&set(self.secret_ring.keys.values()):raise ValueError('BACKUP_SEPARATE_SECRET_KEY_REQUIRED')
        self.store=Store(config,self.ring)
    def initialize(self):
        self.store.initialize()
        with self.db_engine.connect() as db:schema=Repo.source(db)
        identity=hashlib.sha256(canonical({'host':self.db_engine.url.host,'port':self.db_engine.url.port,'database':self.db_engine.url.database,'schema':schema,'environment':self.settings.environment})).hexdigest()
        path=self.config.root/'identity.json'
        with database_lease(self.config.root/'identity'):
            if path.exists():
                if self.ring.read(path)!= {'identity':identity}:raise ValueError('BACKUP_WRONG_ENVIRONMENT')
            else:self.ring.save(path,{'identity':identity})
        return identity
    def locations(self,identity,external=False):
        key(identity)
        if external:
            self.external_ready();return self.config.external/(identity+'.p2b'),self.config.external/'secrets'/(identity+'.p2s')
        return self.config.root/(identity+'.p2b'),self.config.secrets/(identity+'.p2s')
    def external_ready(self):
        root=self.config.external
        if not root or not root.is_dir() or root.is_symlink():raise ValueError('BACKUP_EXTERNAL_UNAVAILABLE')
        marker=root/'.project2-backup-volume'
        if not marker.is_file() or marker.is_symlink() or marker.read_text().strip()!=self.config.external_marker:raise ValueError('BACKUP_EXTERNAL_VOLUME_MISMATCH')
    def create(self,*,kind='full',actor=None):
        if kind not in ('full','checkpoint'):raise ValueError('BACKUP_KIND_INVALID')
        environment=self.initialize();identity=uuid.uuid4().hex;start=time.monotonic();self.store.event('backup','RUNNING',actor=actor,identity=identity)
        try:
            with Repo.lock(self.db_engine) as lock,tempfile.TemporaryDirectory(prefix='backup-',dir=self.config.staging) as raw:
                stage=Path(raw);payload=stage/'payload';private_dir(payload)
                require_postgresql_schema(self.db_engine)
                values=secrets_payload();pause=time.monotonic()
                with self.db_engine.connect().execution_options(isolation_level='REPEATABLE READ') as snapshot:
                    with snapshot.begin():
                        with Repo.freeze(lock):
                            token=snapshot.scalar(text('SELECT pg_export_snapshot()'));schema=Repo.source(snapshot)
                            point=stamp()
                            if set(snapshot.scalars(text('SELECT version_num FROM alembic_version')))!={REVISION}:raise ValueError('BACKUP_SCHEMA_CHANGED')
                            inventory(self.settings.paths['documents'],payload/'documents',immutable=True)
                            inventory(self.settings.paths['photos'],payload/'photos')
                        frozen_seconds=time.monotonic()-pause
                        refs=Repo.references(snapshot);counts=Repo.counts(snapshot);check_mfa(snapshot,values)
                        with Repo.client(self.db_engine.url,stage,schema) as env,private_file(payload/'database.dump') as out:
                            Repo.tool(self.config,'pg_dump',['--format=custom','--no-owner','--no-privileges','--schema='+schema,'--snapshot='+token],env,output=out)
                validate_refs(payload,refs)
                with database_lease(self.config.root/'journal'):
                    self.store.events()
                    publish(self.config.root/'operations.json',payload/'operations.json')
                with private_file(stage/'secrets.json') as out:out.write(canonical(values))
                capsule=stage/'secrets.p2s';self.secret_ring.encrypt(stage/'secrets.json',capsule,limit=1024**2)
                manifest={'format':1,'id':identity,'environment':self.settings.environment,'source_identity':environment,'schema':schema,'revision':REVISION,'release':self.config.release,
                          'snapshot_at':point,'kind':kind,'references':refs,'counts':counts,'secrets_sha256':sha(capsule),'postgresql':17,'freeze_seconds':frozen_seconds}
                manifest=pack(payload,stage/'bundle.tar',manifest)
                used=sum(p.stat().st_size for root in (self.config.root,self.config.secrets) for p in root.rglob('*') if p.is_file() and not p.is_symlink())
                archive=stage/'archive.p2b';self.ring.encrypt(stage/'bundle.tar',archive,limit=self.config.max_bytes-used-capsule.stat().st_size-65536)
                with open_bundle(self.config,self.ring,self.secret_ring,archive,capsule) as (checked,_,__):
                    if checked['id']!=identity:raise ValueError('BACKUP_ID_MISMATCH')
                target,secret=self.locations(identity);publish(capsule,secret);publish(archive,target)
                record={'id':identity,'kind':kind,'snapshot_at':point,'completed_at':stamp(),'size':target.stat().st_size,'sha256':sha(target),'secrets_sha256':sha(secret),'integrity':'VERIFIED','external':'NOT_CONFIGURED','duration_seconds':time.monotonic()-start,'freeze_seconds':frozen_seconds,'release':self.config.release,'revision':REVISION}
                self.store.save('catalog',record)
                if self.config.external:
                    try:
                        self.external_ready();private_dir(self.config.external/'secrets')
                        ext,ext_secret=self.locations(identity,True);publish(target,ext);publish(secret,ext_secret)
                        with open_bundle(self.config,self.ring,self.secret_ring,ext,ext_secret):pass
                        record['external']='VERIFIED';self.store.save('catalog',record);self.ring.save(self.config.external/(identity+'.json'),record)
                    except Exception:
                        record['external']='FAILED';self.store.save('catalog',record);raise ValueError('BACKUP_EXTERNAL_FAILED') from None
                self.store.event('backup','SUCCESS',actor=actor,identity=identity,details={'duration_seconds':record['duration_seconds'],'freeze_seconds':frozen_seconds})
                if self.config.prune:self.prune()
                return record
        except Exception as error:
            code=str(error) if isinstance(error,ValueError) and str(error).startswith('BACKUP_') else 'BACKUP_FAILED'
            self.store.event('backup','FAILED',actor=actor,identity=identity,code=code);self.alert(code,identity)
            raise ValueError(code) from None
    def verify(self,identity,*,actor=None,external=False):
        self.store.event('verify','RUNNING',actor=actor,identity=identity)
        try:
            archive,capsule=self.locations(identity,external)
            with open_bundle(self.config,self.ring,self.secret_ring,archive,capsule) as (manifest,_,__):
                if manifest['id']!=identity:raise ValueError('BACKUP_ID_MISMATCH')
                result={k:manifest[k] for k in ('id','snapshot_at','release','revision','kind','counts')}
            if not external:
                record=self.store.read('catalog',identity)
                if sha(archive)!=record['sha256']:raise ValueError('BACKUP_CATALOG_MISMATCH')
                record['integrity']='VERIFIED';record['verified_at']=stamp();self.store.save('catalog',record)
            self.store.event('verify','SUCCESS',actor=actor,identity=identity);return result
        except Exception as error:
            self.store.event('verify','FAILED',actor=actor,identity=identity,code='BACKUP_VERIFICATION_FAILED')
            if not external:
                try:
                    record=self.store.read('catalog',identity);record['integrity']='CORRUPT';self.store.save('catalog',record)
                except ValueError:pass
            raise ValueError('BACKUP_VERIFICATION_FAILED') from None
    def alert(self,code,identity=None):
        alert={'at':stamp(),'code':code,'backup_id':identity}
        self.ring.save(self.config.root/'alert.json',alert)
        if self.config.alert_command:
            try:subprocess.run(list(self.config.alert_command),input=canonical(alert),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,check=True)
            except (OSError,subprocess.SubprocessError):self.store.event('notification','FAILED',code='BACKUP_NOTIFICATION_FAILED')
    def prune(self):
        # Only authenticated catalog entries owned by this tool. Never legacy backups.
        good=sorted([r for r in self.store.records('catalog') if r['integrity']=='VERIFIED'],key=lambda r:r['snapshot_at'],reverse=True)
        if len(good)<3:return
        for newest in good[:2]:
            try:
                self.verify(newest['id'])
                if self.config.external:self.verify(newest['id'],external=True)
            except ValueError:return # A corrupt newer copy must never authorize deletion of an older good one.
        for row in good[2:]:
            deadline=now()- (timedelta(days=self.config.full_days) if row['kind']=='full' else timedelta(hours=self.config.checkpoint_hours))
            if datetime.fromisoformat(row['snapshot_at'])>=deadline:continue
            if self.config.external and row['external']!='VERIFIED':continue
            # Authenticate all components again before retention can remove anything.
            try:self.verify(row['id'])
            except ValueError:continue
            if self.config.external:
                try:self.verify(row['id'],external=True)
                except ValueError:continue
            self.store.event('retention','SUCCESS',identity=row['id'])
            for external in (False,True) if self.config.external else (False,):
                for path in self.locations(row['id'],external):path.unlink()
                if external:(self.config.external/(row['id']+'.json')).unlink()
            row['integrity']='PRUNED';self.store.save('catalog',row)
    def run_once(self):
        self.initialize()
        with database_lease(self.config.root/'worker'):
            jobs=self.store.records('jobs')
            for job in jobs:
                if job['state']=='RUNNING':
                    job['state']='FAILED';job['code']='BACKUP_WORKER_INTERRUPTED';self.store.save('jobs',job);self.store.event('worker','FAILED',actor=job['actor_user_id'],code=job['code'])
            pending=next((j for j in sorted(jobs,key=lambda j:j['at']) if j['state']=='QUEUED'),None)
            if pending:
                job=pending;job['state']='RUNNING';self.store.save('jobs',job)
                try:
                    from sqlalchemy.orm import Session
                    with Session(self.db_engine) as db:user=Repo.user(db,job['actor_user_id']);allowed=user and user.is_active and user.role=='master'
                    if not allowed or (now()-datetime.fromisoformat(job['at'])).total_seconds()>300:raise ValueError('BACKUP_AUTHORIZATION_EXPIRED')
                    result=self.create(actor=job['actor_user_id']) if job['operation']=='create' else self.verify(job['backup_id'],actor=job['actor_user_id'])
                    job.update(state='SUCCESS',backup_id=result['id'])
                except Exception as error:
                    code=str(error) if isinstance(error,ValueError) and str(error).startswith('BACKUP_') else 'BACKUP_JOB_FAILED'
                    job.update(state='FAILED',code=code);self.store.event('job','FAILED',actor=job['actor_user_id'],code=job['code']);self.alert(job['code'],job.get('backup_id'))
                self.store.save('jobs',job);return job['state']=='SUCCESS'
            due,kind=self.store.due()
            if now()>=due:self.create(kind=kind)
            from .drills import maybe_run
            maybe_run(self)
            return True

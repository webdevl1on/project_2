"""One complete restore point: PostgreSQL snapshot + pinned files + separate secrets."""
from contextlib import contextmanager,nullcontext
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
        self.store=Store(config,self.ring);self._worker_lock=None
    @contextmanager
    def operation_lock(self):
        with database_lease(self.config.root/'worker'),Repo.lock(self.db_engine) as connection:
            self._worker_lock=connection
            try:yield
            finally:self._worker_lock=None
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
    def check_storage(self):
        # Privileged Windows inspection belongs to worker/CLI, never HTTP enqueue.
        if os.name=='nt':
            from .windows_storage import local_root
            paths=(self.config.root,self.config.secrets,self.config.staging,self.config.drill_root)
            for path in dict.fromkeys(p for p in paths if p is not None):local_root(self,path,allow_sids=())
            for path in (self.settings.paths['documents'],self.settings.paths['photos']):local_root(self,path)
            for path in {self.config.key_file.parent,self.config.secrets_key_file.parent}:local_root(self,path,allow_sids=())
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
        if os.name=='nt':
            from .windows_storage import external_root
            external_root(self,root)
    def replicate(self,identity):
        from .safe_files import SafeTree
        self.external_ready();private_dir(self.config.external/'secrets')
        record=self.store.read('catalog',identity);archive,capsule=self.locations(identity)
        try:
            SafeTree(self.config.external).copy(archive,identity+'.p2b',record['sha256'])
            SafeTree(self.config.external).copy(capsule,'secrets/'+identity+'.p2s',record['secrets_sha256'])
            ext,ext_secret=self.locations(identity,True)
            with open_bundle(self.config,self.ring,self.secret_ring,ext,ext_secret):pass
            record['external']='VERIFIED';self.store.save('catalog',record);self.ring.save(self.config.external/(identity+'.json'),record)
            self.store.event('replica','SUCCESS',identity=identity)
        except Exception:
            record['external']='FAILED';self.store.save('catalog',record);raise ValueError('BACKUP_EXTERNAL_FAILED') from None
        return record
    def create(self,*,kind='full',actor=None,job_id=None):
        self.check_storage()
        if kind not in ('full','checkpoint'):raise ValueError('BACKUP_KIND_INVALID')
        environment=self.initialize();identity=uuid.uuid4().hex;start=time.monotonic();self.store.event('backup','RUNNING',actor=actor,identity=identity)
        try:
            with (nullcontext(self._worker_lock) if self._worker_lock is not None else Repo.lock(self.db_engine)) as lock,tempfile.TemporaryDirectory(prefix='backup-',dir=self.config.staging) as raw:
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
                            if self.config.photo_index:publish(self.config.photo_index,payload/'photo-index.json')
                        frozen_seconds=time.monotonic()-pause
                        refs=Repo.references(snapshot);counts=Repo.counts(snapshot);check_mfa(snapshot,values)
                        with Repo.client(self.db_engine.url,stage,schema) as env,private_file(payload/'database.dump') as out:
                            Repo.tool(self.config,'pg_dump',['--format=custom','--no-owner','--no-privileges','--schema='+schema,'--snapshot='+token],env,output=out)
                validate_refs(payload,refs)
                with database_lease(self.config.root/'journal'):
                    self.store.events()
                    publish(self.config.root/'operations.json',payload/'operations.json')
                    inventory(self.config.root/'operations',payload/'operations',immutable=True)
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
                record={'id':identity,'kind':kind,'job_id':job_id,'drill':'NOT_RUN','snapshot_at':point,'completed_at':stamp(),'size':target.stat().st_size,'sha256':sha(target),'secrets_sha256':sha(secret),'integrity':'VERIFIED','external':'NOT_CONFIGURED','duration_seconds':time.monotonic()-start,'freeze_seconds':frozen_seconds,'release':self.config.release,'revision':REVISION}
                self.store.save('catalog',record)
                if self.config.external:
                    try:
                        record=self.replicate(identity)
                    except Exception:
                        record['external']='FAILED';self.store.save('catalog',record);raise ValueError('BACKUP_EXTERNAL_FAILED') from None
                self.store.event('backup','SUCCESS',actor=actor,identity=identity,details={'duration_seconds':record['duration_seconds'],'freeze_seconds':frozen_seconds})
                return record
        except Exception as error:
            code=str(error) if isinstance(error,ValueError) and str(error).startswith('BACKUP_') else 'BACKUP_FAILED'
            self.store.event('backup','FAILED',actor=actor,identity=identity,code=code);self.alert(code,identity)
            raise ValueError(code) from None
    def verify(self,identity,*,actor=None,external=False):
        self.check_storage()
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
        raise ValueError('BACKUP_AUTOMATIC_RETENTION_DISABLED')
    def run_once(self):
        from .worker import run_once
        return run_once(self)

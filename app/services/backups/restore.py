"""Master-controlled, staged restore. Never overwrite an existing working database."""
from datetime import datetime,timedelta
from contextlib import ExitStack
from pathlib import Path
import hashlib,os,re,shutil,tempfile,time,uuid,json
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from app.database.postgresql import require_postgresql_schema
from app.repositories.backup_repository import BackupRepository as Repo,SSL_OPTIONS
from .crypto import canonical,sha,private_dir
from .bundle import open_bundle,check_mfa,validate_refs
from .store import key,now,stamp

def target_url(value):
    try:url=make_url(value)
    except Exception:raise ValueError('RESTORE_TARGET_INVALID') from None
    if url.drivername!='postgresql+psycopg' or not url.host or set(url.query)-SSL_OPTIONS.keys() or not re.fullmatch('project2_restore_[a-f0-9]{8,32}',url.database or ''):raise ValueError('RESTORE_REQUIRES_NEW_ISOLATED_DATABASE')
    return url

def fingerprint(url):return hashlib.sha256(canonical({'host':url.host,'port':url.port or 5432,'database':url.database,'username':url.username,'tls':dict(url.query)})).hexdigest()

def empty(engine):
    with engine.connect() as db:
        if db.scalar(text("SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")):raise ValueError('RESTORE_TARGET_NOT_EMPTY')
        Repo.source(db)

def plan(backup,identity,target,*,actor,reason,external=False):
    backup.store.event('restore_plan','RUNNING',actor=actor,identity=identity)
    try:return _plan(backup,identity,target,actor=actor,reason=reason,external=external)
    except Exception:
        backup.store.event('restore_plan','FAILED',actor=actor,identity=identity,code='RESTORE_PLAN_REFUSED')
        raise

def _plan(backup,identity,target,*,actor,reason,external=False):
    if not isinstance(reason,str) or not reason.strip() or len(reason)>2000:raise ValueError('RESTORE_REASON_REQUIRED')
    url=target_url(target)
    if url.database==backup.db_engine.url.database:raise ValueError('RESTORE_SOURCE_FORBIDDEN')
    archive,capsule=backup.locations(identity,external)
    with open_bundle(backup.config,backup.ring,backup.secret_ring,archive,capsule) as (manifest,_,__):
        if manifest['id']!=identity:raise ValueError('BACKUP_ID_MISMATCH')
        config=backup.config
        engine=create_engine(url,hide_parameters=True)
        try:empty(engine)
        finally:engine.dispose()
        result={'id':uuid.uuid4().hex,'backup_id':identity,'at':stamp(),'expires_at':(now()+timedelta(minutes=30)).isoformat(),'target':fingerprint(url),'database':url.database,'actor_user_id':actor,
                'reason':reason.strip(),'external':external,'archive_sha256':sha(archive),'secrets_sha256':sha(capsule),'snapshot_at':manifest['snapshot_at'],'counts':manifest['counts'],'release':manifest['release'],'revision':manifest['revision']}
    private_dir(config.root/'plans');backup.ring.save(config.root/'plans'/(result['id']+'.json'),result)
    backup.store.event('restore_plan','SUCCESS',actor=actor,identity=identity,details={'plan_id':result['id'],'target':result['database']})
    return result

def apply(backup,plan_id,target,output_root,*,actor,confirmed,authorize=None):
    try:return _apply(backup,plan_id,target,output_root,actor=actor,confirmed=confirmed,authorize=authorize)
    except Exception:
        backup.store.event('restore','FAILED',actor=actor,code='RESTORE_REFUSED_OR_QUARANTINED')
        raise

def _apply(backup,plan_id,target,output_root,*,actor,confirmed,authorize=None):
    if confirmed is not True:raise ValueError('RESTORE_CONFIRMATION_REQUIRED')
    if actor is None and authorize is None:raise ValueError('RESTORE_MASTER_PROOF_REQUIRED')
    result=backup.ring.read(backup.config.root/'plans'/(key(plan_id)+'.json'));url=target_url(target)
    if result['actor_user_id']!=actor or result.get('consumed') or datetime.fromisoformat(result['expires_at'])<=now() or fingerprint(url)!=result['target']:raise ValueError('RESTORE_PLAN_INVALID_OR_EXPIRED')
    output=Path(output_root).resolve()
    public=Path(__file__).resolve().parents[3]/'app'/'static'
    for forbidden in [public,*backup.settings.paths.values(),backup.config.secrets,backup.config.staging,*([backup.config.external] if backup.config.external else [])]:
        if output==forbidden or output in forbidden.parents or forbidden in output.parents:raise ValueError('RESTORE_OUTPUT_OVERLAPS_SOURCE')
    if output.exists() or output.is_symlink():raise ValueError('RESTORE_OUTPUT_MUST_NOT_EXIST')
    archive,capsule=backup.locations(result['backup_id'],result['external'])
    if sha(archive)!=result['archive_sha256'] or sha(capsule)!=result['secrets_sha256']:raise ValueError('RESTORE_COPY_CHANGED')
    start=time.monotonic();config=backup.config
    backup.store.event('restore','RUNNING',actor=actor,identity=result['backup_id'],details={'plan_id':plan_id,'target':url.database})
    # Local lease and a PostgreSQL lease serialize the target even from different hosts/roots.
    from app.database.maintenance import database_lease
    private_dir(output.parent)
    with ExitStack() as locks,database_lease(config.root/('restore-'+fingerprint(url))),open_bundle(config,backup.ring,backup.secret_ring,archive,capsule) as (manifest,values,root):
        result=backup.ring.read(config.root/'plans'/(plan_id+'.json'))
        if result.get('consumed'):raise ValueError('RESTORE_PLAN_ALREADY_CONSUMED')
        engine=create_engine(url,hide_parameters=True,connect_args={'options':'-c timezone=UTC'})
        try:
            locks.enter_context(Repo.lock(engine))
            empty(engine)
            # Consume before any change; a failed target must be inspected, never overwritten on retry.
            result['consumed']=True;backup.ring.save(config.root/'plans'/(plan_id+'.json'),result)
            with tempfile.TemporaryDirectory(prefix='restore-',dir=output.parent) as raw:
                stage=Path(raw);env_stage=stage/'client';private_dir(env_stage)
                with engine.begin() as db:db.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
                with Repo.client(url,env_stage) as env:
                    Repo.tool(config,'pg_restore',['--no-owner','--no-privileges','--exit-on-error','--single-transaction','--dbname='+url.database,str(root/'database.dump')],env)
                engine.dispose();engine=create_engine(url,hide_parameters=True,connect_args={'options':'-c search_path='+manifest['schema']+',public -c timezone=UTC'})
                require_postgresql_schema(engine)
                with engine.connect() as db:
                    if Repo.counts(db)!=manifest['counts']:raise ValueError('RESTORE_ROW_COUNTS_MISMATCH')
                    check_mfa(db,values)
                    if Repo.references(db)!=manifest['references']:raise ValueError('RESTORE_FILE_LINKS_MISMATCH')
                verified_actor=authorize(engine,values) if authorize is not None else actor
                # Copied bearer tokens/unfinished MFA flows must never activate on the recovery site.
                with engine.begin() as db:
                    db.execute(text('DELETE FROM auth_flows'));db.execute(text('DELETE FROM user_sessions'))
                for name in ('documents','photos'):
                    if (root/name).exists():shutil.copytree(root/name,stage/name)
                    else:private_dir(stage/name)
                validate_refs(stage,manifest['references'])
                if (root/'operations.json').exists():shutil.copyfile(root/'operations.json',stage/'prior-operations.json')
                # No plaintext MFA keys are published. Operator provisions them from this separate capsule.
                shutil.copyfile(capsule,stage/'critical-config.p2s');os.chmod(stage/'critical-config.p2s',0o600)
                report={'id':plan_id,'backup_id':result['backup_id'],'schema':manifest['schema'],'target':url.database,'restored_at':stamp(),'restore_seconds':time.monotonic()-start,'snapshot_at':manifest['snapshot_at'],'counts':manifest['counts'],'sessions_revoked':True,'state':'VERIFIED_ISOLATED','confirmed_master_id':verified_actor}
                backup.ring.save(stage/'recovery.json',report)
                shutil.rmtree(env_stage);os.rename(stage,output)
            backup.store.event('restore','SUCCESS',actor=verified_actor,identity=result['backup_id'],details=report)
            return report
        except Exception:
            raise ValueError('RESTORE_FAILED_TARGET_QUARANTINED') from None
        finally:engine.dispose()

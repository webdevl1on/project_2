"""Worker-only copy of a ready archive onto a locally allowlisted BitLocker USB."""
from pathlib import Path
import tempfile,time,uuid,shutil
from . import emergency,windows_storage
from .safe_files import SafeTree,no_links
from .crypto import private_file,canonical,sha
from .store import key,stamp

def available(backup):
    return [{k:v.get(k) for k in ('id','label','root','size','free','eligible')} for v in windows_storage.cached_volumes(backup)]

def export(backup,volume_id,*,actor,job_id=None):
    if backup._worker_lock is None:
        with backup.operation_lock():return export(backup,volume_id,actor=actor,job_id=job_id)
    identity=job_id or uuid.uuid4().hex;key(identity)
    from sqlalchemy.orm import Session
    with Session(backup.db_engine) as db:emergency.authorize_export(db,actor)
    windows_storage.local_root(backup,backup.config.emergency_root)
    manifest=emergency.latest(backup);start=time.monotonic();files=0;size=0
    backup.store.event('usb','RUNNING',actor=actor,details={'job_id':identity})
    try:
        volume,root=windows_storage.select_volume(backup,volume_id)
        destination=windows_storage.secure_usb_root(backup,root);tree=SafeTree(destination)
        version=manifest['path']+'_usb_'+identity
        copies=[(backup.config.emergency_root/manifest['path']/name,version+'/'+name,data['sha256'],data['size']) for name,data in manifest['books'].items()]
        copies.extend((backup.config.emergency_root/r['path'],r['path'],r['sha256'],r['size']) for r in manifest['files'])
        # Keep the complete directory ancestry pinned throughout the job, including
        # between files. The volume GUID plus disk identity is checked at both ends.
        with tree.parent('manifest.json'):
            required=0
            for _,relative,digest,length in copies:
                try:tree.check(relative,digest)
                except FileNotFoundError:required+=length
            if volume['free']<required+1024**2:raise ValueError('USB_INSUFFICIENT_SPACE')
            for source,relative,digest,length in copies:
                no_links(source)
                if tree.copy(source,relative,digest):files+=1;size+=length
            current,_=windows_storage.select_volume(backup,volume_id)
            if windows_storage.identity(current)!=windows_storage.identity(volume):raise ValueError('USB_VOLUME_CHANGED_OR_NOT_ALLOWED')
            for _,relative,digest,_ in copies:tree.check(relative,digest)
            report={**manifest,'path':version,'source_version':manifest['path'],'usb_job_id':identity,'exported_at':stamp()}
            with tempfile.TemporaryDirectory(prefix='usb-',dir=backup.config.staging) as raw:
                source=Path(raw)/'manifest.json'
                with private_file(source) as out:out.write(canonical(report))
                tree.copy(source,version+'/manifest.json',sha(source))
        result={'files':files,'size':size,'seconds':time.monotonic()-start,'version':Path(version).name}
        backup.store.event('usb','SUCCESS',actor=actor,details=result);return result
    except Exception as error:
        code=str(error) if isinstance(error,ValueError) and str(error).startswith(('USB_','STORAGE_')) else 'USB_COPY_FAILED'
        backup.store.event('usb','FAILED',actor=actor,code=code,details={'files':files,'size':size,'seconds':time.monotonic()-start});raise ValueError(code) from None

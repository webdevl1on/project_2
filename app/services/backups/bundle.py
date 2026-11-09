"""Authenticated archive validation. No tar extraction of links or arbitrary paths."""
from contextlib import contextmanager
from pathlib import Path,PurePosixPath
import hashlib,json,os,re,shutil,tarfile,tempfile
from cryptography.fernet import Fernet
from sqlalchemy import text
from app.database.postgresql import REVISION
from app.security.mfa_config import MARKER
from .crypto import private_file,private_dir,sha,canonical

SECRET_NAMES=('PROJECT2_MFA_KEYS','PROJECT2_MFA_CURRENT_KEY','STAFF_SIGNING_KEY','PROJECT2_WEBAUTHN_RP_ID','PROJECT2_WEBAUTHN_ORIGINS')

def secrets_payload():
    values={name:os.environ.get(name,'') for name in SECRET_NAMES}
    if any(not value for value in values.values()):raise ValueError('BACKUP_CRITICAL_CONFIGURATION_MISSING')
    if len(values['STAFF_SIGNING_KEY'])<32:raise ValueError('BACKUP_SIGNING_KEY_REQUIRED')
    return values

def check_mfa(connection,values):
    try:
        keys={k:Fernet(v.encode()) for k,v in json.loads(values['PROJECT2_MFA_KEYS']).items()}
        if values['PROJECT2_MFA_CURRENT_KEY'] not in keys:raise ValueError()
        def decode(value):
            k,token=value.split(':',1);return keys[k].decrypt(token.encode()).decode()
        marker=connection.scalar(text('SELECT ciphertext FROM mfa_key_state WHERE id=1'))
        if not marker or decode(marker)!=MARKER:raise ValueError()
        for cipher in connection.scalars(text('SELECT ciphertext FROM totp_factors UNION ALL SELECT ciphertext FROM auth_flows WHERE ciphertext IS NOT NULL')):decode(cipher)
    except Exception:raise ValueError('BACKUP_MFA_KEYS_MISMATCH') from None

def inventory(source,target,*,immutable=False):
    private_dir(target);result=[]
    if not source.exists():return result
    if source.is_symlink():raise ValueError('BACKUP_SYMLINK_FORBIDDEN')
    for path in sorted(source.rglob('*')):
        if path.is_symlink():raise ValueError('BACKUP_SYMLINK_FORBIDDEN')
        if path.is_dir():continue
        if immutable and path.name.startswith('.pending-'):continue
        if not path.is_file():raise ValueError('BACKUP_SPECIAL_FILE_FORBIDDEN')
        relative=path.relative_to(source);destination=target/relative;private_dir(destination.parent)
        if immutable:
            try:os.link(path,destination)
            except OSError:
                with path.open('rb') as inp,private_file(destination) as out:shutil.copyfileobj(inp,out)
        else:
            with path.open('rb') as inp,private_file(destination) as out:shutil.copyfileobj(inp,out)
        result.append(relative.as_posix())
    return result

def validate_refs(root,refs):
    for record in refs:
        identity=record['storage_key']
        if not re.fullmatch('[a-f0-9]{64}',identity):raise ValueError('BACKUP_FILE_REFERENCE_INVALID')
        path=root/'documents'/identity
        if not path.is_file() or path.is_symlink():raise ValueError('BACKUP_REFERENCED_FILE_MISSING')
        if path.stat().st_size!=record['size'] or sha(path)!=record['sha256']:raise ValueError('BACKUP_FILE_HASH_MISMATCH')

def pack(root,target,manifest):
    members={}
    with tarfile.open(target,'w') as archive:
        os.chmod(target,0o600)
        for path in sorted(root.rglob('*')):
            if not path.is_file():continue
            name=path.relative_to(root).as_posix()
            if name=='manifest.json':raise ValueError('BACKUP_MEMBER_RESERVED')
            members[name]={'size':path.stat().st_size,'sha256':sha(path)}
            archive.add(path,arcname=name,recursive=False)
        manifest={**manifest,'files':members}
        encoded=canonical(manifest)
        import io
        item=tarfile.TarInfo('manifest.json');item.size=len(encoded);item.mode=0o600
        archive.addfile(item,io.BytesIO(encoded))
    return manifest

@contextmanager
def open_bundle(config,ring,secret_ring,archive,capsule):
    with tempfile.TemporaryDirectory(prefix='verify-',dir=config.staging) as raw:
        stage=Path(raw);tar=stage/'verified.tar';secret=stage/'secrets.json';root=stage/'contents';private_dir(root)
        ring.decrypt(archive,tar,limit=config.max_bytes);secret_ring.decrypt(capsule,secret,limit=1024**2)
        try:values=json.loads(secret.read_text())
        except ValueError:raise ValueError('BACKUP_SECRETS_INVALID') from None
        members={};total=0
        try:
            with tarfile.open(tar,'r:') as source:
                for item in source:
                    path=PurePosixPath(item.name)
                    if not item.isfile() or path.is_absolute() or '..' in path.parts or '\\' in item.name or ':' in item.name or item.name in members or len(item.name)>1000:raise ValueError('BACKUP_ARCHIVE_INVALID')
                    if item.name=='manifest.json' and item.size>16*1024**2:raise ValueError('BACKUP_MANIFEST_TOO_LARGE')
                    if item.name not in ('database.dump','manifest.json','operations.json') and not item.name.startswith(('documents/','photos/')):raise ValueError('BACKUP_ARCHIVE_INVALID')
                    total+=item.size
                    if item.size<0 or total>config.max_bytes:raise ValueError('BACKUP_ARCHIVE_TOO_LARGE')
                    target=root.joinpath(*path.parts);private_dir(target.parent)
                    with source.extractfile(item) as inp,private_file(target) as out:shutil.copyfileobj(inp,out)
                    members[item.name]={'size':item.size,'sha256':sha(target)}
            manifest=json.loads((root/'manifest.json').read_text());members.pop('manifest.json')
            if manifest['secrets_sha256']!=sha(capsule):raise ValueError('BACKUP_SECRETS_MISMATCH')
            if manifest['format']!=1 or manifest['revision']!=REVISION or manifest['release']!=config.release:raise ValueError('BACKUP_VERSION_INCOMPATIBLE')
            if manifest['files']!=members or 'database.dump' not in members:raise ValueError('BACKUP_MANIFEST_MISMATCH')
            validate_refs(root,manifest['references'])
        except (tarfile.TarError,KeyError,FileNotFoundError,json.JSONDecodeError):raise ValueError('BACKUP_ARCHIVE_INVALID') from None
        yield manifest,values,root

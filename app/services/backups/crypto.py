"""Streaming AES-256-GCM via cryptography; authenticate before using plaintext."""
import base64,hashlib,hmac,json,os,struct
from pathlib import Path
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag

MAGIC=b'P2BACKUP1\n';BLOCK=1024*1024

def canonical(data):return json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
def private_dir(path):path.mkdir(parents=True,exist_ok=True,mode=0o700)
def private_file(path):return os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb')
def sha(path):
    result=hashlib.sha256()
    with path.open('rb') as source:
        while chunk:=source.read(BLOCK):result.update(chunk)
    return result.hexdigest()

class Keyring:
    def __init__(self,path):
        try:
            if path.is_symlink() or path.stat().st_size>65536 or os.name!='nt' and path.stat().st_mode&0o077:raise ValueError()
            data=json.loads(path.read_text());self.current=data['current'];self.keys={k:base64.b64decode(v,validate=True) for k,v in data['keys'].items()}
            if self.current not in self.keys or any(not isinstance(k,str) or not k or len(k)>80 or len(v)!=32 for k,v in self.keys.items()):raise ValueError()
        except (ValueError,KeyError,TypeError,OSError):raise ValueError('BACKUP_KEY_INVALID') from None
    def mac(self,key,data):
        derived=HKDF(algorithm=hashes.SHA256(),length=32,salt=None,info=b'project2 backup metadata v1').derive(self.keys[key])
        return hmac.new(derived,canonical(data),hashlib.sha256).hexdigest()
    def signed(self,data):return {'key':self.current,'data':data,'mac':self.mac(self.current,data)}
    def read(self,path):
        try:
            if path.is_symlink() or path.stat().st_size>16*1024**2:raise ValueError()
            record=json.loads(path.read_text())
            if not hmac.compare_digest(self.mac(record['key'],record['data']),record['mac']):raise ValueError()
            return record['data']
        except (KeyError,ValueError,TypeError,OSError):raise ValueError('BACKUP_METADATA_INVALID') from None
    def save(self,path,data):
        temporary=path.with_name('.'+path.name+'.'+os.urandom(8).hex())
        try:
            with private_file(temporary) as out:out.write(canonical(self.signed(data)));out.flush();os.fsync(out.fileno())
            os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)
    def encrypt(self,source,target,*,limit):
        header=canonical({'key':self.current,'nonce':base64.b64encode(os.urandom(12)).decode()})
        cipher=Cipher(algorithms.AES(self.keys[self.current]),modes.GCM(base64.b64decode(json.loads(header)['nonce']))).encryptor();cipher.authenticate_additional_data(MAGIC+header)
        created=False
        try:
            out=private_file(target);created=True
            with out,source.open('rb') as inp:
                out.write(MAGIC+struct.pack('>I',len(header))+header)
                while chunk:=inp.read(BLOCK):
                    out.write(cipher.update(chunk))
                    if out.tell()>limit:raise ValueError('BACKUP_QUOTA_EXCEEDED')
                out.write(cipher.finalize()+cipher.tag);out.flush();os.fsync(out.fileno())
                if out.tell()>limit:raise ValueError('BACKUP_QUOTA_EXCEEDED')
        except Exception:
            if created:target.unlink(missing_ok=True)
            raise
    def decrypt(self,source,target,*,limit):
        created=False
        try:
            out=private_file(target);created=True
            with out,source.open('rb') as inp:
                if inp.read(len(MAGIC))!=MAGIC:raise ValueError()
                length=struct.unpack('>I',inp.read(4))[0]
                if not 1<=length<=4096:raise ValueError()
                header=inp.read(length);data=json.loads(header);remaining=source.stat().st_size-inp.tell()-16
                if not 0<=remaining<=limit:raise ValueError()
                cipher=Cipher(algorithms.AES(self.keys[data['key']]),modes.GCM(base64.b64decode(data['nonce'],validate=True))).decryptor();cipher.authenticate_additional_data(MAGIC+header)
                while remaining:
                    chunk=inp.read(min(BLOCK,remaining))
                    if not chunk:raise ValueError()
                    out.write(cipher.update(chunk));remaining-=len(chunk)
                out.write(cipher.finalize_with_tag(inp.read(16)));out.flush();os.fsync(out.fileno())
        except (ValueError,KeyError,TypeError,OSError,InvalidTag,struct.error):
            if created:target.unlink(missing_ok=True)
            raise ValueError('BACKUP_AUTHENTICATION_FAILED') from None

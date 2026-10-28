"""Private local storage, separate from SQLAlchemy and HTTP."""
import hashlib
import os
from pathlib import Path
import re
import secrets

MAX_FILE_SIZE = 10 * 1024 * 1024


class DocumentStorage:
    def __init__(self, root=None):
        self.root=Path(root or os.environ.get('PROJECT2_DOCUMENT_STORAGE','data/private_documents')).resolve()
        from app.config import BASE_DIR
        static=(BASE_DIR/'static').resolve()
        if self.root==static or static in self.root.parents: raise ValueError('Копії не можна зберігати в static.')

    def path(self,key):
        if not re.fullmatch('[a-f0-9]{64}',key): raise ValueError('Некоректний ключ файла.')
        path=self.root/key
        if path.is_symlink() or path.resolve().parent!=self.root: raise ValueError('Неприпустимий шлях файла.')
        return path

    def prepare(self,content):
        if not content or len(content)>MAX_FILE_SIZE: raise ValueError('Розмір копії: від 1 байта до 10 МБ.')
        if content.startswith(b'%PDF-'): mime='application/pdf'
        elif content.startswith(b'\x89PNG\r\n\x1a\n'): mime='image/png'
        elif content.startswith(b'\xff\xd8\xff'): mime='image/jpeg'
        else: raise ValueError('Підтримуються PDF, PNG та JPEG з відповідною сигнатурою.')
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        key=secrets.token_hex(32);temporary=self.root/('.pending-'+key)
        fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(content);stream.flush();os.fsync(stream.fileno())
        except Exception:
            temporary.unlink(missing_ok=True);raise
        return {'key':key,'temporary':temporary,'mime':mime,'size':len(content),'sha256':hashlib.sha256(content).hexdigest()}

    def publish(self,prepared): os.replace(prepared['temporary'],self.path(prepared['key']))

    def discard(self,prepared):
        prepared['temporary'].unlink(missing_ok=True)
        self.path(prepared['key']).unlink(missing_ok=True)

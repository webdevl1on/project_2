"""No-follow directory handles and exclusive, verified, no-replace publication.

Windows directory handles deny FILE_SHARE_DELETE for the entire operation, so a
junction/parent cannot be substituted between validation and publication.
"""
from contextlib import contextmanager,ExitStack
from pathlib import Path,PurePosixPath
import hashlib,os,re,shutil,uuid
from .crypto import BLOCK

def parts(relative):
    path=PurePosixPath(str(relative))
    if path.is_absolute() or not path.parts or any(p in ('.','..') or re.search(r'[<>:"\\|?*\x00-\x1f]',p) or p.endswith((' ','.')) for p in path.parts):raise ValueError('STORAGE_PATH_INVALID')
    return path.parts

def safe_name(value,limit=95):
    value=re.sub(r'[<>:"/\\|?*\x00-\x1f]','_',str(value)).strip(' .')[:limit].rstrip(' .') or 'Без назви'
    if re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?',value):value='_'+value
    return value

def no_links(path):
    path=Path(path).absolute()
    for item in [*reversed(path.parents),path]:
        if item.exists() or item.is_symlink():
            st=item.lstat()
            if item.is_symlink() or getattr(st,'st_file_attributes',0)&0x400:raise ValueError('STORAGE_REPARSE_FORBIDDEN')
    return path

class SafeTree:
    def __init__(self,root):self.root=no_links(root)
    @contextmanager
    def parent(self,relative,create=False):
        names=parts(relative)
        if os.name=='nt':
            with windows_parents(self.root,names[:-1],create) as parent:yield parent,names[-1]
        else:
            with ExitStack() as stack:
                fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY);stack.callback(os.close,fd)
                for name in (*self.root.parts[1:],*names[:-1]):
                    if create:
                        try:os.mkdir(name,0o700,dir_fd=fd)
                        except FileExistsError:pass
                    nxt=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);stack.callback(os.close,nxt);fd=nxt
                yield fd,names[-1]
    def copy(self,source,relative,expected):
        with self.parent(relative,True) as (parent,name):
            if os.name=='nt':return windows_copy(source,parent,name,expected)
            try:
                current=os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
            except FileNotFoundError:current=None
            if current is not None:
                with os.fdopen(current,'rb') as inp:
                    if file_hash(inp)!=expected:raise ValueError('STORAGE_FILE_CONFLICT')
                return False
            tmp='.'+uuid.uuid4().hex+'.partial'
            try:
                fd=os.open(tmp,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=parent)
                with os.fdopen(fd,'w+b') as out,source.open('rb') as inp:
                    shutil.copyfileobj(inp,out,BLOCK);out.flush();os.fsync(out.fileno());out.seek(0)
                    if file_hash(out)!=expected:raise ValueError('STORAGE_CHECKSUM_MISMATCH')
                    os.link(tmp,name,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
                    os.fsync(parent)
                return True
            finally:
                try:os.unlink(tmp,dir_fd=parent)
                except FileNotFoundError:pass
    def check(self,relative,expected):
        with self.parent(relative) as (parent,name):
            if os.name=='nt':
                with windows_read(parent/name) as inp:actual=file_hash(inp)
            else:
                with os.fdopen(os.open(name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent),'rb') as inp:actual=file_hash(inp)
            if actual!=expected:raise ValueError('STORAGE_FILE_CONFLICT')
    def read(self,relative,limit):
        with self.parent(relative) as (parent,name):
            if os.name=='nt':
                with windows_read(parent/name) as inp:result=inp.read(limit+1)
            else:
                with os.fdopen(os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent),'rb') as inp:
                    import stat
                    if not stat.S_ISREG(os.fstat(inp.fileno()).st_mode):raise ValueError('STORAGE_SPECIAL_FILE_FORBIDDEN')
                    result=inp.read(limit+1)
            if len(result)>limit:raise ValueError('STORAGE_METADATA_TOO_LARGE')
            return result

def file_hash(stream):
    digest=hashlib.sha256()
    while chunk:=stream.read(BLOCK):digest.update(chunk)
    return digest.hexdigest()

def winapi():
    import ctypes
    from ctypes import wintypes as w
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateFileW.argtypes=[w.LPCWSTR,w.DWORD,w.DWORD,w.LPVOID,w.DWORD,w.DWORD,w.HANDLE];api.CreateFileW.restype=w.HANDLE
    api.CloseHandle.argtypes=[w.HANDLE];api.CloseHandle.restype=w.BOOL
    api.GetFileInformationByHandleEx.argtypes=[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD];api.GetFileInformationByHandleEx.restype=w.BOOL
    api.SetFileInformationByHandle.argtypes=[w.HANDLE,ctypes.c_int,w.LPVOID,w.DWORD];api.SetFileInformationByHandle.restype=w.BOOL
    return ctypes,w,api

def win_open(path,*,directory=False,write=False):
    c,w,api=winapi()
    access=0x80000000|(0x40000000|0x10000 if write else 0)
    flags=0x00200000|(0x02000000 if directory else 0) # OPEN_REPARSE_POINT, BACKUP_SEMANTICS
    handle=api.CreateFileW(str(path),access,1,None,1 if write else 3,flags,None)
    if handle==w.HANDLE(-1).value:raise c.WinError(c.get_last_error())
    # FILE_ATTRIBUTE_TAG_INFO includes the reparse flag even with OPEN_REPARSE_POINT.
    info=(w.DWORD*2)()
    if not api.GetFileInformationByHandleEx(handle,9,c.byref(info),c.sizeof(info)) or info[0]&0x400:
        api.CloseHandle(handle);raise ValueError('STORAGE_REPARSE_FORBIDDEN')
    return handle

@contextmanager
def windows_parents(root,names,create):
    c,w,api=winapi()
    with ExitStack() as stack:
        current=Path(root.anchor)
        for name in ('',*root.parts[1:],*names):
            if name:current=current/name
            if create:
                try:current.mkdir()
                except FileExistsError:pass
            handle=win_open(current,directory=True);stack.callback(api.CloseHandle,handle)
        yield current

@contextmanager
def windows_read(path):
    import msvcrt
    handle=win_open(path)
    with os.fdopen(msvcrt.open_osfhandle(handle,os.O_RDONLY|os.O_BINARY),'rb') as inp:yield inp

def windows_copy(source,parent,name,expected):
    import msvcrt
    c,w,api=winapi();target=parent/name
    try:
        with windows_read(target) as inp:
            if file_hash(inp)!=expected:raise ValueError('STORAGE_FILE_CONFLICT')
            return False
    except FileNotFoundError:pass
    temporary=parent/('.'+uuid.uuid4().hex+'.partial');handle=win_open(temporary,write=True)
    # open_osfhandle transfers ownership; keep it until handle-based rename completes.
    with os.fdopen(msvcrt.open_osfhandle(handle,os.O_RDWR|os.O_BINARY),'w+b') as out:
        try:
            with source.open('rb') as inp:shutil.copyfileobj(inp,out,BLOCK)
            out.flush();os.fsync(out.fileno());out.seek(0)
            if file_hash(out)!=expected:raise ValueError('STORAGE_CHECKSUM_MISMATCH')
            class Rename(c.Structure):_fields_=[('Flags',w.DWORD),('RootDirectory',w.HANDLE),('FileNameLength',w.DWORD),('FileName',w.WCHAR*1)]
            encoded=str(target).encode('utf-16-le');offset=Rename.FileName.offset;buffer=c.create_string_buffer(offset+len(encoded));info=Rename.from_buffer(buffer)
            info.Flags=0;info.RootDirectory=None;info.FileNameLength=len(encoded);c.memmove(c.addressof(buffer)+offset,encoded,len(encoded))
            if not api.SetFileInformationByHandle(handle,3,buffer,len(buffer)):raise c.WinError(c.get_last_error())
        except Exception:
            disposition=w.BOOL(True);api.SetFileInformationByHandle(handle,4,c.byref(disposition),c.sizeof(disposition))
            raise
    return True

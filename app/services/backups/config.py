"""Explicit deployment configuration; secrets never enter the public status DTO."""
from dataclasses import dataclass
from pathlib import Path
import json,os,re,subprocess

@dataclass(frozen=True)
class BackupConfig:
    root:Path
    secrets:Path
    staging:Path
    key_file:Path
    secrets_key_file:Path
    external:Path|None=None
    external_marker:str=''
    interval_minutes:int=60
    daily_hour:int=2
    full_days:int=14
    checkpoint_hours:int=48
    max_bytes:int=100*1024**3
    prune:bool=False
    alert_command:tuple=()
    tool_dir:str=''
    release:str=''
    drill_root:Path|None=None
    drill_hours:int=168
    drill_each_backup:bool=True
    emergency_root:Path|None=None
    emergency_hour:int=18
    emergency_enabled:bool=False
    emergency_max_bytes:int=100*1024**3
    usb_volume_ids:tuple=()
    archive_sids:tuple=()
    service_sids:tuple=()
    photo_index:Path|None=None

    @classmethod
    def load(cls,settings):
        filename=os.environ.get('PROJECT2_BACKUP_CONFIG')
        if not filename:raise ValueError('BACKUP_NOT_CONFIGURED')
        try:data=json.loads(Path(filename).read_text(encoding='utf-8'))
        except (OSError,ValueError):raise ValueError('BACKUP_CONFIG_INVALID') from None
        if not isinstance(data,dict):raise ValueError('BACKUP_CONFIG_INVALID')
        paths={key:Path(data.pop(key)).resolve() for key in ('secrets','staging','key_file','secrets_key_file')}
        external=data.pop('external',None)
        if external:paths['external']=Path(external).resolve()
        for name in ('emergency_root','photo_index'):
            if data.get(name):paths[name]=Path(data.pop(name)).absolute()
        if data.get('drill_root'):paths['drill_root']=Path(data.pop('drill_root')).resolve()
        config=cls(root=settings.paths['backups'],**paths,**data)
        config.validate(settings.paths)
        return config

    def validate(self,source_paths):
        if not self.release or len(self.release)>100 or not re.fullmatch(r'[A-Za-z0-9_.-]+',self.release):raise ValueError('BACKUP_RELEASE_REQUIRED')
        for value,low,high in [(self.interval_minutes,1,60),(self.daily_hour,0,23),(self.full_days,1,3650),(self.checkpoint_hours,1,8760),(self.max_bytes,1024,2**60),(self.drill_hours,1,8760)]:
            if type(value) is not int or not low<=value<=high:raise ValueError('BACKUP_CONFIG_INVALID')
        if self.prune:raise ValueError('BACKUP_AUTOMATIC_RETENTION_DISABLED')
        if self.drill_each_backup is not True or type(self.emergency_enabled) is not bool or type(self.emergency_hour) is not int or not 0<=self.emergency_hour<=23 or type(self.emergency_max_bytes) is not int or self.emergency_max_bytes<1024:raise ValueError('BACKUP_CONFIG_INVALID')
        if any(not isinstance(v,str) for v in (*self.usb_volume_ids,*self.archive_sids,*self.service_sids)):raise ValueError('BACKUP_CONFIG_INVALID')
        if self.emergency_enabled and not self.emergency_root:raise ValueError('EMERGENCY_ROOT_REQUIRED')
        if type(self.prune) is not bool or not isinstance(self.alert_command,(list,tuple)) or any(not isinstance(v,str) for v in self.alert_command):raise ValueError('BACKUP_CONFIG_INVALID')
        if self.external and not re.fullmatch('[A-Za-z0-9_-]{8,100}',self.external_marker):raise ValueError('BACKUP_EXTERNAL_MARKER_REQUIRED')
        if self.staging.exists() and os.name!='nt' and self.staging.stat().st_mode&0o077:raise ValueError('BACKUP_STAGING_NOT_PRIVATE')
        roots=[self.root,self.secrets,self.staging,*([self.external] if self.external else []),*([self.drill_root] if self.drill_root else []),source_paths['documents'],source_paths['photos'],*([self.emergency_root] if self.emergency_root else [])]
        if any(a==b or a in b.parents or b in a.parents for i,a in enumerate(roots) for b in roots[i+1:]):raise ValueError('BACKUP_PATHS_MUST_BE_SEPARATE')
        repo=Path(__file__).resolve().parents[3]
        public=repo/'app'/'static'
        if any(root==public or public in root.parents for root in roots):raise ValueError('BACKUP_PUBLIC_PATH_FORBIDDEN')
        if self.photo_index:
            if self.photo_index==repo or repo in self.photo_index.parents:raise ValueError('EMERGENCY_PHOTO_INDEX_MUST_BE_PRIVATE')
            from .safe_files import no_links
            no_links(self.photo_index)
        for key in (self.key_file,self.secrets_key_file):
            if key==repo or repo in key.parents or any(key==r or r in key.parents for r in roots):raise ValueError('BACKUP_KEYS_MUST_BE_SEPARATE')
        for root in roots:
            from .safe_files import no_links
            no_links(root)

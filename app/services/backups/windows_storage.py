"""Server-side, fail-closed Windows storage inspection. No drive from HTTP input."""
import hashlib,json,os,subprocess,re
from datetime import datetime,timedelta
from pathlib import Path
from .safe_files import no_links,SafeTree
from .store import now,stamp

# Static script; only a trusted local path is passed through the child environment.
SCRIPT=r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$me=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rows=@()
foreach($disk in Get-Disk) {
 foreach($part in Get-Partition -DiskNumber $disk.Number) {
  $v=$part | Get-Volume -ErrorAction SilentlyContinue
  if(!$v -or !$v.DriveLetter) { continue }
  $mount="$($v.DriveLetter):\"
  $b=Get-BitLockerVolume -MountPoint $mount
  $rows+=@{volume_id=$v.UniqueId;disk_id=$disk.UniqueId;serial=$disk.SerialNumber;bus="$($disk.BusType)";readonly=[bool]$disk.IsReadOnly;offline=[bool]$disk.IsOffline;root=$mount;label=$v.FileSystemLabel;fs=$v.FileSystem;free=[long]$v.SizeRemaining;size=[long]$v.Size;protection="$($b.ProtectionStatus)";lock="$($b.LockStatus)";encryption="$($b.VolumeStatus)";percent=[int]$b.EncryptionPercentage}
 }
}
$acl=$null
if($env:PROJECT2_STORAGE_INSPECT_PATH) {
 $path=$env:PROJECT2_STORAGE_INSPECT_PATH
 while(!(Test-Path -LiteralPath $path)) { $path=Split-Path -Parent $path }
 $a=Get-Acl -LiteralPath $path
 $rules=@($a.Access | ForEach-Object {@{sid=$_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value;type="$($_.AccessControlType)";rights=[long]$_.FileSystemRights}})
 $acl=@{protected=$a.AreAccessRulesProtected;rules=$rules}
}
@{volumes=@($rows);acl=$acl;worker_sid=$me} | ConvertTo-Json -Depth 6 -Compress
'''

def inspect_storage(path=None):
    if os.name!='nt':raise ValueError('STORAGE_WINDOWS_REQUIRED')
    env=os.environ.copy();env['PROJECT2_STORAGE_INSPECT_PATH']=str(path) if path else ''
    try:
        result=subprocess.run(['powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-Command',SCRIPT],env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=60,check=True)
        return json.loads(result.stdout.decode('utf-8-sig'))
    except (OSError,ValueError,subprocess.SubprocessError):raise ValueError('STORAGE_INSPECTION_FAILED') from None

def encrypted(volume):
    return volume.get('fs')=='NTFS' and volume.get('protection')=='On' and volume.get('lock')=='Unlocked' and volume.get('encryption')=='FullyEncrypted' and volume.get('percent')==100 and not volume.get('readonly') and not volume.get('offline')

def identity(volume):
    return hashlib.sha256(json.dumps([volume.get(k,'') for k in ('volume_id','disk_id','serial')],ensure_ascii=True).encode()).hexdigest()

def private_acl(report,allowed):
    acl=report.get('acl') or {};sids={*allowed,report.get('worker_sid'),'S-1-5-18','S-1-5-32-544'}
    if not acl.get('protected') or not acl.get('rules'):raise ValueError('STORAGE_NTFS_ACL_REQUIRED')
    # Any unapproved ALLOW is rejected, including inherited broad read permissions.
    if any(r.get('type')=='Allow' and r.get('sid') not in sids and r.get('rights',0) for r in acl['rules']):raise ValueError('STORAGE_NTFS_ACL_REQUIRED')

def local_root(backup,path,*,allow_sids=None):
    path=no_links(path)
    if backup.settings.environment=='testing' and os.name!='nt':
        if path.exists() and path.stat().st_mode&0o077:raise ValueError('STORAGE_PRIVATE_DIRECTORY_REQUIRED')
        return
    report=inspect_storage(path);matches=[v for v in report['volumes'] if str(path).casefold().startswith(v['root'].casefold())]
    if len(matches)!=1 or not encrypted(matches[0]) or matches[0].get('bus')=='USB':raise ValueError('STORAGE_ENCRYPTED_INTERNAL_DISK_REQUIRED')
    private_acl(report,(*backup.config.service_sids,*(backup.config.archive_sids if allow_sids is None else allow_sids)))

def external_root(backup,path):
    path=no_links(path);report=inspect_storage(path)
    matches=[v for v in report['volumes'] if str(path).casefold().startswith(v['root'].casefold()) or str(path).casefold().startswith(v['volume_id'].casefold())]
    if len(matches)!=1 or not encrypted(matches[0]):raise ValueError('STORAGE_ENCRYPTED_DISK_REQUIRED')
    if matches[0]['bus']=='USB' and matches[0]['volume_id'].casefold() not in {s.casefold() for s in backup.config.usb_volume_ids}:raise ValueError('USB_VOLUME_CHANGED_OR_NOT_ALLOWED')
    private_acl(report,backup.config.service_sids)

def volumes(backup):
    report=inspect_storage();allowed={v.casefold() for v in backup.config.usb_volume_ids};result=[]
    for volume in report['volumes']:
        if volume.get('bus')!='USB' or volume.get('volume_id','').casefold() not in allowed:continue
        result.append({**volume,'id':identity(volume),'eligible':encrypted(volume)})
    return result

def select_volume(backup,identifier):
    matches=[v for v in volumes(backup) if v['id']==identifier]
    if len(matches)!=1:raise ValueError('USB_VOLUME_CHANGED_OR_NOT_ALLOWED')
    volume=matches[0]
    if not volume['eligible']:raise ValueError('USB_BITLOCKER_REQUIRED')
    # Use the volume GUID path, never the mutable drive letter selected in a browser.
    root=Path(volume['volume_id'])
    if not re.fullmatch(r'\\\\\?\\Volume\{[0-9a-fA-F-]{36}\}\\?',str(root)):raise ValueError('USB_VOLUME_ID_INVALID')
    no_links(root)
    return volume,root

def secure_usb_root(backup,root):
    target=root/'Project_2';no_links(target)
    created=not target.exists()
    # Pin every ancestor before running ACL tools; junction substitution must not
    # redirect even this preparatory filesystem write outside the USB root.
    with SafeTree(root).parent('Project_2/manifest.json',True):
      if created:
        # Protect ACL before any personal data is copied. Values are SID-only and
        # validated here, never taken from a web request or concatenated script.
        report=inspect_storage();sids=[report['worker_sid'],'S-1-5-18','S-1-5-32-544',*backup.config.service_sids,*backup.config.archive_sids]
        if any(not re.fullmatch(r'S-1-\d+(?:-\d+)+',s) for s in sids):raise ValueError('STORAGE_SID_INVALID')
        service_count=3+len(backup.config.service_sids)
        args=['icacls.exe',str(target),'/inheritance:r','/grant:r',*[s+':(OI)(CI)F' for s in sids[:service_count]],*[s+':(OI)(CI)R' for s in sids[service_count:]]]
        try:subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=True)
        except (OSError,subprocess.SubprocessError):raise ValueError('STORAGE_NTFS_ACL_REQUIRED') from None
      private_acl(inspect_storage(target),(*backup.config.service_sids,*backup.config.archive_sids))
    excel=target/'Excel';created_excel=not excel.exists()
    with SafeTree(root).parent('Project_2/Excel/manifest.json',True):
        if created_excel:
            report=inspect_storage();sids=[report['worker_sid'],'S-1-5-18','S-1-5-32-544',*backup.config.service_sids,*backup.config.archive_sids]
            if any(not re.fullmatch(r'S-1-\d+(?:-\d+)+',s) for s in sids):raise ValueError('STORAGE_SID_INVALID')
            service_count=3+len(backup.config.service_sids)
            args=['icacls.exe',str(excel),'/inheritance:r','/grant:r',*[s+':(OI)(CI)F' for s in sids[:service_count]],*[s+':(OI)(CI)M' for s in sids[service_count:]]]
            try:subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=True)
            except (OSError,subprocess.SubprocessError):raise ValueError('STORAGE_NTFS_ACL_REQUIRED') from None
        private_acl(inspect_storage(excel),(*backup.config.service_sids,*backup.config.archive_sids))
    return target

def refresh_devices(backup):
    """Privileged read-only discovery runs in the OS worker, never the HTTP process."""
    if os.name!='nt':return
    path=backup.config.root/'devices.json'
    try:data={'at':stamp(),'volumes':volumes(backup),'code':None}
    except ValueError:data={'at':stamp(),'volumes':[],'code':'USB_INSPECTION_FAILED'}
    previous=backup.ring.read(path) if path.exists() else {}
    backup.ring.save(path,data)
    if data['code'] and previous.get('code')!=data['code']:backup.store.event('usb_probe','FAILED',code=data['code'])

def cached_volumes(backup):
    try:report=backup.ring.read(backup.config.root/'devices.json')
    except ValueError:raise ValueError('USB_WORKER_DISCOVERY_REQUIRED') from None
    if report.get('code') or datetime.fromisoformat(report['at'])+timedelta(minutes=5)<=now():raise ValueError('USB_WORKER_DISCOVERY_REQUIRED')
    return report['volumes']

def check_request(backup,identifier):
    if not isinstance(identifier,str):raise ValueError('USB_VOLUME_ID_INVALID')
    matches=[v for v in cached_volumes(backup) if v['id']==identifier and v['volume_id'].casefold() in {s.casefold() for s in backup.config.usb_volume_ids}]
    if len(matches)!=1 or not matches[0]['eligible']:raise ValueError('USB_BITLOCKER_REQUIRED')

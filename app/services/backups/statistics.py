"""Weekly signed measurements. Counting never cleans permanent artifacts."""
from datetime import datetime,timedelta
from pathlib import Path
import shutil,uuid
from sqlalchemy import text
from .safe_files import no_links
from .crypto import private_dir
from .store import now,stamp

def measure(path):
    size=files=0
    if path is None:return {'size':0,'files':0,'free':None}
    path=no_links(path)
    if path.exists():
        for file in path.rglob('*'):
            no_links(file)
            if file.is_file():size+=file.stat().st_size;files+=1
    existing=path
    while not existing.exists():existing=existing.parent
    return {'size':size,'files':files,'free':shutil.disk_usage(existing).free}

def collect(backup,*,actor=None):
    backups=measure(backup.config.root);capsules=measure(backup.config.secrets)
    excel=measure(backup.config.emergency_root/'Excel' if backup.config.emergency_root else None)
    documents=measure(backup.config.emergency_root/'Документи' if backup.config.emergency_root else None)
    with backup.db_engine.connect() as db:
        database=db.scalar(text('SELECT pg_database_size(current_database())'))
    artifacts=[p for root,pattern in ((backup.config.root,'*.p2b'),(backup.config.secrets,'*.p2s')) for p in root.glob(pattern) if p.is_file()]
    for p in artifacts:no_links(p)
    result={'id':uuid.uuid4().hex,'at':stamp(),'database_size':database,
            'backups':{**backups,'size':sum(p.stat().st_size for p in artifacts),'files':len(artifacts),'count':sum(p.suffix=='.p2b' for p in artifacts)},
            'excel':excel,'documents':documents}
    total=database+result['backups']['size']+excel['size']+documents['size']
    previous=[v for v in backup.store.records('statistics') if datetime.fromisoformat(v['at'])<=now()-timedelta(days=7)]
    baseline=max(previous,key=lambda r:r['at']) if previous else None
    result.update(total_size=total,growth_7_days=total-baseline['total_size'] if baseline else None,baseline_at=baseline['at'] if baseline else None)
    events=backup.store.events();success=[e for e in events if e['result']=='SUCCESS'];failure=[e for e in events if e['result']=='FAILED']
    result.update(last_success=success[-1]['at'] if success else None,last_failure=failure[-1]['at'] if failure else None)
    result['low_space']=any(v['free'] is not None and v['free']<max(1024**3,total//10) for v in (backups,capsules,excel,documents))
    private_dir(backup.config.root/'statistics');backup.store.save('statistics',result)
    backup.store.event('statistics','SUCCESS',actor=actor,details={'total_size':total,'low_space':result['low_space']})
    if result['low_space']:backup.alert('STORAGE_LOW_SPACE')
    return result

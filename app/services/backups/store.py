"""Private durable jobs/catalog and authenticated chained operational journal."""
from datetime import datetime,UTC,timedelta
from pathlib import Path
import json,os,re,uuid
from app.database.maintenance import database_lease
from .crypto import canonical,private_dir

def now():return datetime.now(UTC)
def stamp():return now().isoformat()
def key(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{32}',value):raise ValueError('BACKUP_ID_INVALID')
    return value

class Store:
    def __init__(self,config,ring):self.config=config;self.ring=ring;self.root=config.root
    def initialize(self):
        for path in (self.root,self.config.secrets,self.config.staging,self.root/'jobs',self.root/'catalog'):private_dir(path)
    def records(self,kind):
        directory=self.root/kind
        return [self.ring.read(p) for p in sorted(directory.glob('*.json'))] if directory.exists() else []
    def save(self,kind,data):self.ring.save(self.root/kind/(key(data['id'])+'.json'),data)
    def read(self,kind,identity):return self.ring.read(self.root/kind/(key(identity)+'.json'))
    def events(self):
        path=self.root/'operations.json'
        if not path.exists():return []
        try:
            journal=self.ring.read(path);previous='0'*64;result=[]
            for envelope in journal['events']:
                data=envelope['data']
                if data['previous']!=previous or self.ring.mac(envelope['key'],data)!=envelope['mac']:raise ValueError()
                previous=envelope['mac'];result.append(data)
            if journal['last']!=previous:raise ValueError()
            return result
        except (KeyError,ValueError,TypeError):raise ValueError('BACKUP_JOURNAL_INVALID') from None
    def event(self,operation,result,*,actor=None,identity=None,code=None,details=None):
        self.initialize()
        with database_lease(self.root/'journal'):
            self.events() # Authenticate before extending, including after a restart/key rotation.
            path=self.root/'operations.json'
            journal=self.ring.read(path) if path.exists() else {'events':[],'last':'0'*64}
            data={'id':uuid.uuid4().hex,'at':stamp(),'operation':operation,'result':result,'actor_user_id':actor,'backup_id':identity,'code':code,'details':details or {},'previous':journal['last']}
            envelope=self.ring.signed(data);journal['events'].append(envelope);journal['last']=envelope['mac']
            # Atomic replace of one authenticated envelope: crash leaves the previous or complete new journal.
            self.ring.save(path,journal)
    def enqueue(self,operation,actor,identity=None):
        if operation not in ('create','verify'):raise ValueError('BACKUP_OPERATION_INVALID')
        if identity:key(identity)
        self.initialize()
        with database_lease(self.root/'queue'):
            for job in self.records('jobs'):
                if job['state'] in ('QUEUED','RUNNING') and job['operation']==operation and job.get('backup_id')==identity:return job
            job={'id':uuid.uuid4().hex,'at':stamp(),'state':'QUEUED','operation':operation,'actor_user_id':actor,'backup_id':identity}
            self.event('enqueue','QUEUED',actor=actor,identity=identity);self.save('jobs',job);return job
    def due(self,records=None):
        records=self.records('catalog') if records is None else records
        good=[r for r in records if r['integrity']=='VERIFIED']
        latest=max((datetime.fromisoformat(r['snapshot_at']) for r in good),default=None)
        full=max((datetime.fromisoformat(r['snapshot_at']) for r in good if r['kind']=='full'),default=None)
        day=now().replace(hour=self.config.daily_hour,minute=0,second=0,microsecond=0)
        full_due=day if full is None or full<day else day+timedelta(days=1)
        checkpoint=latest+timedelta(minutes=self.config.interval_minutes) if latest else now()
        return min(full_due,checkpoint),('full' if now()>=full_due else 'checkpoint')
    def status(self):
        records=sorted(self.records('catalog'),key=lambda r:r['snapshot_at'],reverse=True)
        for r in records:
            if r['integrity']=='VERIFIED' and (not (self.root/(r['id']+'.p2b')).is_file() or not (self.config.secrets/(r['id']+'.p2s')).is_file()):r['integrity']='MISSING'
        events=self.events();next_time,kind=self.due(records)
        good=[r for r in records if r['integrity']=='VERIFIED'];failures=[r for r in events if r['result']=='FAILED']
        external_good=[r for r in good if r['external']=='VERIFIED']
        available=False
        if self.config.external:
            marker=self.config.external/'.project2-backup-volume'
            try:available=marker.is_file() and not marker.is_symlink() and marker.read_text().strip()==self.config.external_marker
            except OSError:pass
        drills=[e for e in events if e['operation']=='drill' and e['result']=='SUCCESS']
        return {'configured':True,'backups':records,'jobs':self.records('jobs'),'last_success':good[0] if good else None,'last_failure':failures[-1] if failures else None,
                'next_at':next_time.isoformat(),'next_kind':kind,'external_configured':self.config.external is not None,'external_available':available,
                'external_overdue':bool(self.config.external) and (not external_good or (now()-datetime.fromisoformat(external_good[0]['snapshot_at'])).total_seconds()>3600),
                'drill_configured':bool(self.config.drill_root and (self.root/'drill-permit.json').exists()),'last_drill':drills[-1] if drills else None,
                'rpo_overdue':not good or (now()-datetime.fromisoformat(good[0]['snapshot_at'])).total_seconds()>3600,'events':events[-100:]}

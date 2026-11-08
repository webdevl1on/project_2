"""One deny-first evaluator for every source. No client-provided actor or cached grants."""
from datetime import datetime,UTC
from zoneinfo import ZoneInfo
from app.models import User,Person,Position
from app.models.access import *
from app.access_catalog import CATEGORIES,actions
from app.repositories.access_repository import AccessRepository as Repo


def now():return datetime.now(UTC).replace(tzinfo=None)
def calendar(stamp):return stamp.replace(tzinfo=UTC).astimezone(ZoneInfo('Europe/Kyiv')).date()
def valid(row,stamp):return not getattr(row,'revoked_at',None) and getattr(row,'is_active',True) and (not row.starts_at or row.starts_at<=stamp) and (not row.ends_at or stamp<row.ends_at)

def actor(db,actor_id=None,*,include_inactive=False):
    key=actor_id if actor_id is not None else db.info.get('access_actor')
    user=Repo.get(db,User,key) if key is not None else None
    if user is not None and not db.is_modified(user):db.refresh(user)
    if user is None or not user.is_active and not include_inactive:raise PermissionError('Потрібен ідентифікований користувач.')
    return user

class Access:
    def __init__(self,db,user_id=None,*,at=None,include_inactive=False):
        self.db=db;self.user=actor(db,user_id,include_inactive=include_inactive);self.at=at or now();self.on=calendar(self.at)
        units,states=Repo.topology(db,self.on);living={u.id for u in units}
        self.states={s.org_unit_id:s for s in states if s.org_unit_id in living}
        self.parents={key:s.primary_parent_id for key,s in self.states.items()}
        positions,current,previous=Repo.subjects(db,self.on)
        self.positions={p.position_id:p for p in positions};self.current={a.person_id:a for a in current}
        self.past={}
        for a in previous:self.past.setdefault(a.person_id,[]).append(a)
        templates={t.id:t for t in Repo.all(db,AccessTemplate) if t.is_active}
        assignments=[a for a in Repo.all(db,TemplateAssignment) if a.user_id==self.user.id and a.template_id in templates and valid(a,self.at)]
        policies={p.id:p for p in Repo.all(db,PositionAccessPolicy) if p.is_active}
        own=self.current.get(self.user.person_id)
        self.policy_units={key:self.positions[own.staff_position_id].managed_unit_id for key,p in policies.items()
                           if own and p.position_id==own.staff_position_id and self.positions[own.staff_position_id].managed_unit_id in living}
        temp={t.id:t for t in Repo.all(db,TemporaryAccess) if t.user_id==self.user.id and valid(t,self.at)}
        self.rules=[]
        self.can_manage_rules=self.user.role in ('master','admin') or any(d.user_id==self.user.id and valid(d,self.at) for d in Repo.all(db,AccessDelegation))
        for r in Repo.rules(db,self.user.id,{a.template_id for a in assignments},set(self.policy_units),set(temp)):
            if not valid(r,self.at):continue
            base={'id':r.id,'category':r.category,'action':r.action,'effect':r.effect,'scope_type':r.scope_type,'unit_id':r.unit_id,'position_id':r.position_id,'person_id':r.person_id}
            if r.user_id:self.rules.append({**base,'source':'manual'})
            elif r.template_id:
                self.rules.extend({**base,'scope_type':'unit','unit_id':a.unit_id,'source':'template','source_id':a.id} for a in assignments if a.template_id==r.template_id)
            elif r.policy_id in self.policy_units:self.rules.append({**base,'scope_type':'unit','unit_id':self.policy_units[r.policy_id],'source':'position','source_id':r.policy_id})
            elif r.temporary_id in temp:self.rules.append({**base,'source':'temporary','source_id':r.temporary_id})
    def descendants(self,root,unit):
        seen=set()
        while unit is not None and unit not in seen:
            if unit==root:return root in self.states
            seen.add(unit);unit=self.parents.get(unit)
        return False
    def matches(self,rule,pid=None,position_id=None,unit_id=None):
        if rule['scope_type']=='global':return True
        if pid is not None and rule['scope_type']=='person':return rule['person_id']==pid
        if position_id is None and pid in self.current:position_id=self.current[pid].staff_position_id
        if rule['scope_type']=='position':return rule['position_id']==position_id
        if unit_id is None and position_id in self.positions:unit_id=self.positions[position_id].org_unit_id
        return rule['scope_type']=='unit' and self.descendants(rule['unit_id'],unit_id)
    def decision(self,category,action='read',*,person_id=None,position_id=None,unit_id=None,historical_basic=True):
        if action not in actions(category):raise ValueError('Невідома дія категорії.')
        if not self.user.is_active:return {'allowed':False,'reason':'Обліковий запис вимкнено','rules':[]}
        if self.user.role=='admin':return {'allowed':True,'reason':'Захищені предметні повноваження Admin','rules':[]}
        matching=[r for r in self.rules if r['category']==category and self.matches(r,person_id,position_id,unit_id)]
        relevant=[r for r in matching if r['action'] in ({'read','edit'} if action=='read' else {action,'read'} if action=='edit' else {action})]
        denied=[r for r in relevant if r['effect']=='DENY' and (r['action']==action or action=='edit' and r['action']=='read')]
        allows=[r for r in relevant if r['effect']=='ALLOW' and (r['action']==action or action=='read' and r['action']=='edit')]
        # Former members retain only the expressly agreed minimal basic view.
        # A personal/global DENY still applies. No old medical/service/history access.
        if not denied and not allows and category=='basic' and action=='read' and historical_basic and person_id:
            for previous in self.past.get(person_id,[]):
                old=self.decision('basic','read',position_id=previous.staff_position_id,historical_basic=False)
                if old['allowed']:return {'allowed':True,'reason':'Мінімальний перегляд колишнього військовослужбовця','rules':old['rules']}
        return {'allowed':not denied and bool(allows),'reason':'Явна заборона' if denied else 'Чинні дозволи' if allows else 'Дозвіл відсутній','rules':relevant}
    def allowed(self,category,action='read',**scope):return self.decision(category,action,**scope)['allowed']
    def person_ids(self,category,action='read'):
        ids=set(self.current)|set(self.past)|{r['person_id'] for r in self.rules if r['person_id']}
        if self.user.role=='admin':return None
        if any(r['scope_type']=='global' for r in self.rules):ids.update(p.person_id for p in Repo.all(self.db,Person))
        return {pid for pid in ids if self.allowed(category,action,person_id=pid)}
    def position_ids(self,category='service',action='read'):
        return {key for key in self.positions if self.allowed(category,action,position_id=key)}


def require(db,category,action='read',*,person_id=None,position_id=None,unit_id=None,actor_id=None):
    evaluator=Access(db,actor_id)
    if not evaluator.allowed(category,action,person_id=person_id,position_id=position_id,unit_id=unit_id):
        raise PermissionError('Недостатньо прав доступу до цієї категорії та області.')
    return evaluator


def system_manager(db,user_id):
    user=actor(db,user_id)
    if user.role not in ('master','admin'):raise PermissionError('Потрібні системні повноваження Master/Admin.')
    return user


def require_document(db,person_id,key,action='read',actor_id=None):
    e=require(db,'documents',action,person_id=person_id,actor_id=actor_id)
    if key in Repo.medical_document_ids(db,person_id) and not e.allowed('medical',action,person_id=person_id):
        raise PermissionError('Недостатньо прав на медичний документ.')
    return e

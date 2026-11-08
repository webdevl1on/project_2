"""Atomic, audited ACL administration. Delegation never confers system roles."""
from contextlib import contextmanager
from datetime import datetime,UTC
from app.models import User,Person,Position
from app.models.organization import OrgUnit
from app.models.access import *
from app.repositories.access_repository import AccessRepository as Repo
from app.services import access,accounts
from app.database.transactions import service_transaction
from app.access_catalog import actions,catalog


def reason(value):
    if not isinstance(value,str) or not value.strip() or len(value)>2000:raise ValueError('Вкажіть причину до 2000 символів.')
    return value.strip()

def timestamp(value,required=False):
    if value in (None,''):
        if required:raise ValueError('Потрібен строк чинності.')
        return None
    if isinstance(value,str):
        try:value=datetime.fromisoformat(value.replace('Z','+00:00'))
        except ValueError:raise ValueError('Некоректна дата й час.') from None
    if not isinstance(value,datetime) or value.tzinfo is None:raise ValueError('Дата й час повинні містити часовий пояс.')
    return value.astimezone(UTC).replace(tzinfo=None)

def bounds(start,end,required=False):
    start=timestamp(start,required);end=timestamp(end,required)
    if start and end and start>=end:raise ValueError('Завершення має бути пізніше початку.')
    return start,end

def snapshot(row):
    return {c.name:(v.replace(tzinfo=UTC).isoformat() if isinstance(v,datetime) else v) for c in row.__table__.columns if c.name not in ('created_at','updated_at') for v in [getattr(row,c.name)]}

def audit(db,actor,operation,why,*,target=None,before=None,after=None):
    Repo.add(db,AccessAudit(actor_user_id=actor,target_user_id=target,operation=operation,reason=why,before=before or {},after=after or {}));db.flush()

def fresh(db,user):
    from app.repositories.account_repository import AccountRepository
    from app.services.mfa import fresh as is_fresh,live
    session=AccountRepository.session(db,db.info.get('access_session_hash',''))
    if session is None or session.user_id!=user.id or not live(session) or not is_fresh(session):raise PermissionError('MFA_REAUTH_REQUIRED: потрібне свіже підтвердження MFA.')

@contextmanager
def write(db,actor_id,why):
    why=reason(why)
    with service_transaction(db,immediate=True):
        Repo.lock(db);user=access.actor(db,actor_id);fresh(db,user)
        yield user,why

def target(db,actor,key,revision=None):
    user=Repo.get(db,User,key)
    if user is None:raise ValueError('Користувача не знайдено.')
    if user.role=='admin':raise PermissionError('Предметні повноваження Admin захищені й не редагуються матрицею.')
    if user.role=='master' and actor.role!='master':raise PermissionError('Повноваження Master змінює лише Master.')
    if revision is not None and user.revision!=revision:raise ValueError('Матриця користувача змінилася. Оновіть її.')
    return user

def validate_rule(db,data,*,relative=False):
    if not isinstance(data,dict):raise ValueError('Некоректне правило.')
    category=data.get('category');action=data.get('action');effect=data.get('effect','ALLOW')
    if action not in actions(category) or effect not in ('ALLOW','DENY'):raise ValueError('Невідома дія або ефект правила.')
    scope='relative' if relative else data.get('scope_type');ids={key:None for key in ('unit_id','position_id','person_id')}
    if scope not in ('global','unit','position','person','relative') or scope=='relative' and not relative:raise ValueError('Невідома область правила.')
    for kind,model in [('unit',OrgUnit),('position',Position),('person',Person)]:
        if scope==kind:
            try:key=int(data.get(kind+'_id'))
            except (TypeError,ValueError):raise ValueError('Виберіть реальну область правила.') from None
            row=Repo.get(db,model,key)
            if row is None or getattr(row,'annulled_at',None):raise ValueError('Об’єкт області не існує або анульований.')
            ids[kind+'_id']=key
    start,end=bounds(data.get('starts_at'),data.get('ends_at'))
    return {**ids,'scope_type':scope,'category':category,'action':action,'effect':effect,'starts_at':start,'ends_at':end}

def may_manage_rule(db,actor,user,values):
    if actor.role in ('master','admin'):return
    if user.id==actor.id or user.role!='user':raise PermissionError('Не можна змінювати власні або системні повноваження.')
    evaluator=access.Access(db,actor.id)
    for d in Repo.all(db,AccessDelegation):
        if d.user_id!=actor.id or not access.valid(d,access.now()):continue
        if [values['category'],values['action']] not in d.capabilities:continue
        if values['scope_type']=='unit' and evaluator.descendants(d.unit_id,values['unit_id']):return
        if values['scope_type']=='position':
            p=evaluator.positions.get(values['position_id'])
            if p and evaluator.descendants(d.unit_id,p.org_unit_id):return
        if values['scope_type']=='person':
            a=evaluator.current.get(values['person_id']);p=evaluator.positions.get(a.staff_position_id) if a else None
            if p and evaluator.descendants(d.unit_id,p.org_unit_id):return
    raise PermissionError('Делегування не дозволяє змінювати цю область, категорію або дію.')

def save_rule(db,actor_id,user_id,data,revision,why):
    if type(revision) is not int:raise ValueError('Потрібна актуальна revision матриці.')
    with write(db,actor_id,why) as (actor,why):
        user=target(db,actor,user_id,revision);values=validate_rule(db,data);may_manage_rule(db,actor,user,values)
        row=Repo.add(db,AccessRule(user_id=user.id,created_by=actor.id,**values));user.revision+=1;db.flush()
        audit(db,actor.id,'rule_add',why,target=user.id,after=snapshot(row));key=row.id
    return key

def revoke_rule(db,actor_id,key,revision,why):
    with write(db,actor_id,why) as (actor,why):
        row=Repo.get(db,AccessRule,key)
        if row is None or not row.user_id or row.revoked_at or row.revision!=revision:raise ValueError('Правило вже змінено або недоступне.')
        user=target(db,actor,row.user_id);may_manage_rule(db,actor,user,snapshot(row));before=snapshot(row)
        row.revoked_at=access.now();user.revision+=1;db.flush()
        audit(db,actor.id,'rule_revoke',why,target=user.id,before=before,after=snapshot(row))

def link_person(db,actor_id,user_id,person_id,revision,why):
    with write(db,actor_id,why) as (actor,why):
        access.system_manager(db,actor.id);user=Repo.get(db,User,user_id)
        if user is None or user.revision!=revision:raise ValueError('Користувач змінився.')
        if user.role in ('master','admin') and actor.role!='master':raise PermissionError('Системний акаунт змінює лише Master.')
        if person_id is not None:
            if Repo.get(db,Person,person_id) is None:raise ValueError('Анкету не знайдено.')
            if any(u.person_id==person_id and u.id!=user_id for u in Repo.all(db,User)):raise ValueError('Ця анкета вже прив’язана до іншого акаунта.')
        before={'person_id':user.person_id};user.person_id=person_id
        audit(db,actor.id,'person_link',why,target=user.id,before=before,after={'person_id':person_id})


def template(db,actor_id,name,rules,why,*,key=None,revision=None,confirmed=False,copy_from=None,is_active=True):
    with write(db,actor_id,why) as (actor,why):
        access.system_manager(db,actor.id)
        if not isinstance(name,str) or not name.strip() or len(name)>200:raise ValueError('Назва шаблону: до 200 символів.')
        row=Repo.get(db,AccessTemplate,key) if key else AccessTemplate(name=name.strip())
        if key and (row is None or row.revision!=revision):raise ValueError('Шаблон змінився.')
        affected=[a for a in Repo.all(db,TemplateAssignment) if a.template_id==key and a.is_active] if key else []
        if affected and not confirmed:raise ValueError(f'Підтвердьте централізовану зміну для {len(affected)} призначень шаблону.')
        if type(is_active) is not bool:raise ValueError('Ознака активності повинна бути логічною.')
        old={**snapshot(row),'rules':[snapshot(r) for r in Repo.all(db,AccessRule) if r.template_id==key and not r.revoked_at]} if key else {};row.name=name.strip();row.is_active=is_active;row.revision=(row.revision or 0)+1;Repo.add(db,row);db.flush()
        if copy_from:
            source=Repo.get(db,AccessTemplate,copy_from)
            if source is None:raise ValueError('Шаблон для копіювання відсутній.')
            rules=[snapshot(r) for r in Repo.all(db,AccessRule) if r.template_id==copy_from and not r.revoked_at]
        values=[validate_rule(db,data,relative=True) for data in rules]
        for r in Repo.all(db,AccessRule):
            if r.template_id==row.id and not r.revoked_at:r.revoked_at=access.now()
        for value in values:Repo.add(db,AccessRule(template_id=row.id,created_by=actor.id,**value))
        audit(db,actor.id,'template_change' if key else 'template_create',why,before=old,after={'id':row.id,'name':row.name,'active':row.is_active,'rules':rules,'affected_users':sorted({a.user_id for a in affected})})
        return row.id

def assign_template(db,actor_id,user_id,template_id,unit_id,start,end,why):
    with write(db,actor_id,why) as (actor,why):
        access.system_manager(db,actor.id);user=target(db,actor,user_id)
        if not Repo.get(db,AccessTemplate,template_id) or not Repo.get(db,OrgUnit,unit_id):raise ValueError('Шаблон або підрозділ відсутній.')
        start,end=bounds(start,end)
        row=Repo.add(db,TemplateAssignment(user_id=user.id,template_id=template_id,unit_id=unit_id,starts_at=start,ends_at=end));db.flush()
        audit(db,actor.id,'template_assign',why,target=user.id,after=snapshot(row));return row.id

def policy(db,actor_id,position_id,rules,why,*,revision=None,confirmed=False,is_active=True):
    with write(db,actor_id,why) as (actor,why):
        access.system_manager(db,actor.id)
        p=Repo.get(db,Position,position_id)
        if p is None or p.org_unit_id is None or p.managed_unit_id is None or p.annulled_at:raise ValueError('Потрібна чинна керівна посада з явним підпорядкованим підрозділом.')
        row=next((r for r in Repo.all(db,PositionAccessPolicy) if r.position_id==position_id),None)
        if row and row.revision!=revision:raise ValueError('Політика посади змінилася.')
        if not confirmed:raise ValueError('Підтвердьте затвердження базових прав посади.')
        if type(is_active) is not bool:raise ValueError('Ознака активності повинна бути логічною.')
        row=row or PositionAccessPolicy(position_id=position_id);before={**snapshot(row),'rules':[snapshot(r) for r in Repo.all(db,AccessRule) if r.policy_id==row.id and not r.revoked_at]} if row.id else {};row.is_active=is_active;row.revision=(row.revision or 0)+1;Repo.add(db,row);db.flush()
        for r in Repo.all(db,AccessRule):
            if r.policy_id==row.id and not r.revoked_at:r.revoked_at=access.now()
        for data in rules:Repo.add(db,AccessRule(policy_id=row.id,created_by=actor.id,**validate_rule(db,data,relative=True)))
        audit(db,actor.id,'position_policy',why,before=before,after={'policy_id':row.id,'position_id':position_id,'rules':rules,'active':row.is_active})
        return row.id

def temporary(db,actor_id,user_id,position_id,rules,start,end,why):
    with write(db,actor_id,why) as (actor,why):
        access.system_manager(db,actor.id);user=target(db,actor,user_id)
        p=Repo.get(db,Position,position_id)
        policy=next((r for r in Repo.all(db,PositionAccessPolicy) if r.position_id==position_id and r.is_active),None)
        if p is None or p.managed_unit_id is None or policy is None:raise ValueError('Для цієї посади немає затвердженої політики.')
        policy_rules=[r for r in Repo.all(db,AccessRule) if r.policy_id==policy.id and access.valid(r,access.now())]
        permitted={(r.category,r.action,r.effect) for r in policy_rules}
        values=[validate_rule(db,r,relative=True) for r in rules]
        if not values or any((r['category'],r['action'],r['effect']) not in permitted for r in values):raise PermissionError('Тимчасові права мають бути підмножиною затвердженої політики посади.')
        # Removing optional ALLOWs must never remove a policy's restrictive DENY.
        for r in policy_rules:
            if r.effect=='DENY' and not any(v['category']==r.category and v['action']==r.action and v['effect']=='DENY' for v in values):values.append(validate_rule(db,{'category':r.category,'action':r.action,'effect':'DENY'},relative=True))
        start,end=bounds(start,end,True);row=Repo.add(db,TemporaryAccess(user_id=user.id,position_id=position_id,unit_id=p.managed_unit_id,starts_at=start,ends_at=end));db.flush()
        for value in values:Repo.add(db,AccessRule(temporary_id=row.id,created_by=actor.id,**{**value,'scope_type':'unit','unit_id':p.managed_unit_id,'starts_at':None,'ends_at':None}))
        audit(db,actor.id,'temporary_grant',why,target=user.id,after={'grant':snapshot(row),'rules':[{k:v for k,v in r.items() if k not in ('starts_at','ends_at')} for r in values]});return row.id

def delegation(db,actor_id,user_id,unit_id,capabilities,start,end,why):
    with write(db,actor_id,why) as (actor,why):
        access.system_manager(db,actor.id);user=target(db,actor,user_id)
        if user.role!='user' or actor.id==user_id:raise PermissionError('Делегування доступне тільки іншому звичайному User.')
        if not Repo.get(db,OrgUnit,unit_id):raise ValueError('Підрозділ відсутній.')
        if not isinstance(capabilities,list) or not capabilities:raise ValueError('Виберіть делеговані дії.')
        for item in capabilities:
            if not isinstance(item,list) or len(item)!=2 or item[1] not in actions(item[0]):raise ValueError('Невідома делегована дія.')
        start,end=bounds(start,end,True);row=Repo.add(db,AccessDelegation(delegator_id=actor.id,user_id=user_id,unit_id=unit_id,capabilities=capabilities,starts_at=start,ends_at=end));db.flush()
        audit(db,actor.id,'delegate',why,target=user_id,after=snapshot(row));return row.id

def change_source(db,actor_id,kind,key,revision,active,why):
    models={'template_assignment':TemplateAssignment,'temporary':TemporaryAccess,'delegation':AccessDelegation}
    if kind not in models:raise ValueError('Невідоме джерело.')
    with write(db,actor_id,why) as (actor,why):
        access.system_manager(db,actor.id);row=Repo.get(db,models[kind],key)
        if row is None or row.revision!=revision:raise ValueError('Джерело змінилося.')
        target(db,actor,row.user_id)
        before=snapshot(row)
        if kind=='template_assignment':row.is_active=bool(active)
        elif active:raise ValueError('Відкликаний фіксований набір не поновлюється; створіть новий.')
        else:row.revoked_at=access.now()
        db.flush()
        audit(db,actor.id,'source_activate' if active else 'source_revoke',why,target=row.user_id,before=before,after=snapshot(row))

def resolve_review(db,actor_id,key,revision,why):
    with write(db,actor_id,why) as (actor,why):
        access.system_manager(db,actor.id);row=Repo.get(db,AccessReview,key)
        if row is None or row.status!='OPEN' or row.revision!=revision:raise ValueError('Завдання вже змінено.')
        before=snapshot(row);row.status='RESOLVED';row.decision=why;row.decided_by=actor.id
        db.flush()
        audit(db,actor.id,'review_resolve',why,target=row.user_id,before=before,after=snapshot(row))


def save_matrix(db,actor_id,user_id,changes,revision,why):
    if type(revision) is not int:raise ValueError('Потрібна актуальна revision матриці.')
    if not isinstance(changes,list) or len(changes)>2000:raise ValueError('Некоректна кількість змін матриці.')
    with write(db,actor_id,why) as (actor,why):
        user=target(db,actor,user_id,revision);old=[];added=[]
        for change in changes:
            effect=change.get('effect');values=validate_rule(db,{**change,'effect':effect if effect!='INHERIT' else 'ALLOW'})
            may_manage_rule(db,actor,user,values)
            for row in Repo.all(db,AccessRule):
                if row.user_id==user.id and not row.revoked_at and all(getattr(row,k)==values[k] for k in ('scope_type','unit_id','position_id','person_id','category','action')) and access.valid(row,access.now()):
                    old.append(snapshot(row));row.revoked_at=access.now()
            if effect!='INHERIT':
                row=Repo.add(db,AccessRule(user_id=user.id,created_by=actor.id,**values));db.flush();added.append(snapshot(row))
        user.revision+=1;audit(db,actor.id,'matrix_change',why,target=user.id,before={'rules':old},after={'rules':added})


def can_manage(db,actor_id):
    user=access.actor(db,actor_id)
    if user.role in ('master','admin'):return user
    if any(d.user_id==user.id and access.valid(d,access.now()) for d in Repo.all(db,AccessDelegation)):return user
    raise PermissionError('Керування правами не делеговано.')

def matrix(db,actor_id,user_id):
    from app.services.organization import OrganizationService
    manager=can_manage(db,actor_id);user=Repo.get(db,User,user_id)
    if user is None:raise ValueError('Користувача не знайдено.')
    system=manager.role in ('master','admin')
    if not system and (user.role!='user' or user.id==manager.id):raise PermissionError('Цей акаунт поза межами делегування.')
    e=access.Access(db,user_id,include_inactive=True)
    topology=OrganizationService.tree(db,access.calendar(access.now()))
    positions=[p for p in Repo.all(db,Position) if p.annulled_at is None]
    # Matrix metadata contains organizational labels, never personnel records.
    rows=[{'key':f'unit:{u["id"]}','id':u['id'],'scope_type':'unit','unit_id':u['id'],'position_id':None,'person_id':None,'parent':f'unit:{u["parent_id"]}' if u['parent_id'] else None,'label':u['name']} for u in topology['units']]
    rows.insert(0,{'key':'global:all','id':None,'scope_type':'global','unit_id':None,'position_id':None,'person_id':None,'parent':None,'label':'Усі підрозділи й анкети (глобальне правило)'})
    rows += [{'key':f'position:{p.position_id}','id':p.position_id,'scope_type':'position','position_id':p.position_id,'unit_id':None,'person_id':None,'parent':f'unit:{p.org_unit_id}' if p.org_unit_id else None,'label':f'№{p.position_number} — {p.name_short}'} for p in positions]
    manual=[r for r in Repo.all(db,AccessRule) if r.user_id==user_id and not r.revoked_at]
    if not system:
        def permitted(values):
            try:may_manage_rule(db,manager,user,values);return True
            except PermissionError:return False
        visible={r['key'] for r in rows if any(permitted({**r,'category':c['key'],'action':a}) for c in catalog() for a in c['actions'])}
        ancestors={r['key']:r['parent'] for r in rows}
        for key in list(visible):
            seen=set();parent=ancestors.get(key)
            while parent and parent not in seen:
                seen.add(parent);visible.add(parent);parent=ancestors.get(parent)
        rows=[r for r in rows if r['key'] in visible]
        manual=[r for r in manual if permitted(snapshot(r))]
    for row in rows:
        scope={} if row['scope_type']=='global' else {row['scope_type']+'_id':row['id']}
        if not system:row['manageable']=[c['key']+':'+a for c in catalog() for a in c['actions'] if permitted({**row,'category':c['key'],'action':a})]
        row['effective']={c['key']+':'+a:e.allowed(c['key'],a,**scope) for c in catalog() for a in c['actions'] if system or c['key']+':'+a in row['manageable']}
    def owned(model):return [snapshot(r) for r in Repo.all(db,model) if r.user_id==user_id]
    return {'user':accounts.account_snapshot(user),'linked_person_id':user.person_id,'catalog':catalog(),'rows':rows,'manual':[snapshot(r) for r in manual],
        'system_manager':system,'editable':user.role!='admin' and (user.role!='master' or manager.role=='master') and (system or user_id!=actor_id),
        'template_assignments':owned(TemplateAssignment) if system else [],'temporary':owned(TemporaryAccess) if system else [],'delegations':owned(AccessDelegation) if system else []}


def overview(db,actor_id):
    manager=can_manage(db,actor_id);system=manager.role in ('master','admin')
    return {'system_manager':system,'catalog':catalog(),
        'users':[accounts.account_snapshot(u) for u in Repo.all(db,User) if system or u.role=='user' and u.id!=actor_id],
        'templates':[snapshot(r) for r in Repo.all(db,AccessTemplate)] if system else [],
        'policies':[snapshot(r) for r in Repo.all(db,PositionAccessPolicy)] if system else [],
        'policy_rules':[snapshot(r) for r in Repo.all(db,AccessRule) if r.policy_id and not r.revoked_at] if system else [],
        'reviews':[snapshot(r) for r in Repo.all(db,AccessReview)] if system else [],
        'audit':[snapshot(r) for r in Repo.audit(db)] if system else []}


def explain(db,actor_id,user_id,category,action,scope):
    access.system_manager(db,actor_id)
    return access.Access(db,user_id,include_inactive=True).decision(category,action,**scope)


def template_data(db,actor_id,key):
    access.system_manager(db,actor_id);row=Repo.get(db,AccessTemplate,key)
    if row is None:raise ValueError('Шаблон відсутній.')
    return {**snapshot(row),'rules':[snapshot(r) for r in Repo.all(db,AccessRule) if r.template_id==key and not r.revoked_at]}

def proposal(db,actor_id,position_id):
    access.system_manager(db,actor_id)
    p=Repo.get(db,Position,position_id)
    if p is None or p.managed_unit_id is None:raise ValueError('Виберіть керівну посаду з підпорядкованим підрозділом.')
    row=next((r for r in Repo.all(db,PositionAccessPolicy) if r.position_id==position_id and r.is_active),None)
    return {'unit_id':p.managed_unit_id,'policy_id':row.id if row else None,'revision':row.revision if row else None,
            'rules':[snapshot(r) for r in Repo.all(db,AccessRule) if row and r.policy_id==row.id and not r.revoked_at]}

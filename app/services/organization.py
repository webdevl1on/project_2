"""Effective organizational tree, independent of staffing versions and assignments."""
from app.services.access_context import actor_operation
from contextlib import contextmanager
from datetime import date,datetime,UTC,timedelta
from unicodedata import normalize as unicode_normalize
from app.models.organization import OrgUnit,OrgUnitState,OperationalSubordination,OrgAudit,KINDS,ROSTER_KINDS,level_of
from app.models.staff import exact_date
from app.repositories.organization_repository import OrganizationRepository as Repo
from app.services.staff_service import write_unit,period
from app.services.accounts import authorize as authorize_account

UNSET=object()
ACTIONS=frozenset({'view','manage','create','edit','reparent','reorder','bind','import','dissolve','annul','operational','coverage','map','withdraw','position','position_annul','reassignment'})

@actor_operation
def authorize(db,actor_id,action,unit_id=None):
    """Evaluate the requested organizational action separately from other edits."""
    if action not in ACTIONS:raise ValueError('Невідома організаційна операція.')
    user=authorize_account(db,actor_id)
    if user.role=='admin':return user
    from app.services.access import Access
    e=Access(db,actor_id);mapped={'view':'read','reorder':'reorder','reparent':'reparent','bind':'bind','map':'bind','import':'import'}.get(action,'edit')
    allowed=e.allowed('organization',mapped,unit_id=unit_id) if unit_id is not None else any(e.allowed('organization',mapped,unit_id=key) for key in e.states) or e.allowed('organization',mapped)
    if not allowed:raise PermissionError('Недостатньо організаційних прав для цієї дії.')
    return user

def normalize(name):
    if not isinstance(name,str) or not name.strip() or len(name)>500:raise ValueError('Назва підрозділу: 1–500 символів.')
    return ' '.join(unicode_normalize('NFC',name).split()).casefold()

def reason(value):
    if not isinstance(value,str) or not value.strip() or len(value)>2000:raise ValueError('Вкажіть причину до 2000 символів.')
    return value.strip()

@contextmanager
def organization_write(db,actor_id,action='manage'):
    with write_unit(db):
        Repo.lock(db)
        authorize(db,actor_id,action)
        previous=db.info.get('access_org_action');db.info['access_org_action']=action
        try:yield
        finally:
            if previous is None:db.info.pop('access_org_action',None)
            else:db.info['access_org_action']=previous

def checked(db,key,revision=None):
    unit=Repo.get(db,key)
    if unit is None:raise ValueError('Підрозділ не існує.')
    if unit.annulled_at is not None:raise ValueError('Підрозділ анульовано; створіть новий ID для нового формування.')
    if revision is not None and unit.revision!=revision:raise ValueError('Підрозділ змінився. Оновіть дані.')
    return unit

def active(unit,on):return unit.annulled_at is None and unit.formed_on<=on<= (unit.dissolved_on or date.max)

def state_at(states,key,on):
    return next((s for s in states if s.org_unit_id==key and s.valid_from<=on<= (s.valid_to or date.max)),None)

def explicit_level(kind,value):
    if kind=='other':
        if type(value) is not int or not 1<=value<=7:raise ValueError('Для іншого підрозділу явно вкажіть ієрархічний рівень від 1 до 7.')
        return value
    if value is not None:raise ValueError('Для визначеного типу ієрархічний рівень задано автоматично.')
    return None

def hierarchy_edge(child,parent):
    child_level,parent_level=level_of(child),level_of(parent)
    if child_level is None or parent_level is None:raise ValueError('Спочатку явно визначте ієрархічний рівень іншого підрозділу.')
    if child_level<=parent_level:raise ValueError('Недопустима ієрархія: дочірній підрозділ має бути нижчого рівня за батьківський.')

def snapshot(db,unit):
    return {'id':unit.id,'kind':unit.kind,'hierarchy_level':level_of(unit),'formed_on':unit.formed_on.isoformat(),'dissolved_on':unit.dissolved_on.isoformat() if unit.dissolved_on else None,
            'sort_order':unit.sort_order,'revision':unit.revision,'annulled_at':unit.annulled_at.isoformat() if unit.annulled_at else None,
            'annulment_reason':unit.annulment_reason,'annulled_by':unit.annulled_by,
            'states':[{'id':s.id,'name':s.name,'normalized_name':s.normalized_name,'primary_parent_id':s.primary_parent_id,
                       'valid_from':s.valid_from.isoformat(),'valid_to':s.valid_to.isoformat() if s.valid_to else None} for s in Repo.states(db,unit.id)]}

def audit(db,unit,actor,operation,before,why=None,**values):
    db.flush()
    Repo.add(db,OrgAudit(org_unit_id=unit.id,actor_user_id=actor,operation=operation,before=before,after={**snapshot(db,unit),**values},reason=why))
    db.flush()

def validate_tree(db,strict_unit=None):
    """Check all effective boundaries; future/past cycles and sibling collisions count."""
    db.flush();units={u.id:u for u in Repo.units(db) if u.annulled_at is None};states=Repo.states(db)
    boundaries=set()
    for unit in units.values():
        boundaries.add(unit.formed_on)
        if unit.dissolved_on and unit.dissolved_on<date.max:boundaries.add(unit.dissolved_on+timedelta(days=1))
    relevant=[s for s in states if s.org_unit_id in units]
    by_unit={key:[] for key in units}
    for s in relevant:
        unit=units[s.org_unit_id]
        if s.valid_from<unit.formed_on or (unit.dissolved_on and (s.valid_to is None or s.valid_to>unit.dissolved_on)):
            raise ValueError('Історія підрозділу виходить за період його існування.')
        by_unit[s.org_unit_id].append(s);boundaries.add(s.valid_from)
        if s.valid_to and s.valid_to<date.max:boundaries.add(s.valid_to+timedelta(days=1))
    for edge in Repo.operational(db):
        if edge.org_unit_id not in units:continue
        if edge.parent_id not in units:raise ValueError('Оперативне підпорядкування посилається на анульований підрозділ.')
        for unit in (units[edge.org_unit_id],units[edge.parent_id]):
            if edge.valid_from<unit.formed_on or (unit.dissolved_on and (edge.valid_to is None or edge.valid_to>unit.dissolved_on)):
                raise ValueError('Оперативне підпорядкування виходить за період існування підрозділу.')
    for on in sorted(boundaries):
        current={};siblings=set()
        for key,unit in units.items():
            if not active(unit,on):continue
            matches=[s for s in by_unit[key] if s.valid_from<=on<= (s.valid_to or date.max)]
            if len(matches)!=1:raise ValueError('Підрозділ повинен мати один стан на кожну дату існування.')
            item=matches[0];current[key]=item
            sibling=(item.primary_parent_id,item.normalized_name)
            if sibling in siblings:raise ValueError('Однакові назви одночасно активних дітей одного батьківського підрозділу.')
            siblings.add(sibling)
        for key,item in current.items():
            if item.primary_parent_id is not None and item.primary_parent_id not in current:
                raise ValueError('Батьківський підрозділ не існує протягом усього обраного періоду; спочатку змініть підпорядкування дітей.')
        if strict_unit in current:
            children={key:[] for key in current}
            for key,item in current.items():
                if item.primary_parent_id in children:children[item.primary_parent_id].append(key)
            stack=[strict_unit];seen=set()
            while stack:
                key=stack.pop()
                if key in seen:continue
                seen.add(key)
                if level_of(units[key]) is None:raise ValueError('Спочатку явно визначте ієрархічні рівні всього дочірнього дерева.')
                stack.extend(children[key])
        for key,item in current.items():
            if item.primary_parent_id is not None:
                child,parent=units[key],units[item.primary_parent_id]
                # Legacy other units remain unclassified until an explicit audited decision.
                if level_of(child) is not None and level_of(parent) is not None:hierarchy_edge(child,parent)
        # Iterative traversal supports arbitrary depth without Python recursion limits.
        complete=set()
        for key in current:
            trail=set();cursor=key
            while cursor is not None and cursor not in complete:
                if cursor in trail:raise ValueError('Цикл основного підпорядкування заборонений.')
                trail.add(cursor);cursor=current[cursor].primary_parent_id
            complete.update(trail)

class OrganizationService:
    @staticmethod
    @actor_operation
    def create(db,actor_id,kind,name,formed_on,*,parent_id=None,dissolved_on=None,hierarchy_level=None):
        with organization_write(db,actor_id,'create'):
            return create_locked(db,actor_id,kind,name,formed_on,parent_id=parent_id,dissolved_on=dissolved_on,hierarchy_level=hierarchy_level)

    @staticmethod
    @actor_operation
    def revise(db,actor_id,key,revision,effective_from,*,name=None,parent_id=UNSET,hierarchy_level=UNSET):
        exact_date(effective_from)
        with organization_write(db,actor_id,'reparent' if parent_id is not UNSET and name is None else 'edit'):
            unit=checked(db,key,revision);before=snapshot(db,unit);states=Repo.states(db,key);old=state_at(states,key,effective_from)
            if old is None or not active(unit,effective_from):raise ValueError('Дата не належить періоду існування підрозділу.')
            if parent_id is not UNSET and parent_id is not None:checked(db,parent_id)
            new_name=old.name if name is None else name.strip() if isinstance(name,str) else name
            normalized=normalize(new_name);parent=old.primary_parent_id if parent_id is UNSET else parent_id
            parent_changed=parent!=old.primary_parent_id
            if parent_changed:
                authorize(db,actor_id,'reparent',key)
                if parent is not None:authorize(db,actor_id,'reparent',parent)
            if new_name!=old.name:authorize(db,actor_id,'edit',key)
            if hierarchy_level is not UNSET:
                authorize(db,actor_id,'edit',key)
                if unit.kind!='other':raise ValueError('Рівень визначеного типу не редагується.')
                unit.hierarchy_level=explicit_level(unit.kind,hierarchy_level)
            if parent!=old.primary_parent_id and parent is not None:hierarchy_edge(unit,checked(db,parent))
            if hierarchy_level is UNSET or name is not None or parent_id is not UNSET:
                end=old.valid_to
                if effective_from==old.valid_from:
                    old.name=new_name;old.normalized_name=normalized;old.primary_parent_id=parent
                else:
                    old.valid_to=effective_from-timedelta(days=1);db.flush()
                    Repo.add(db,OrgUnitState(org_unit_id=key,name=new_name,normalized_name=normalized,primary_parent_id=parent,valid_from=effective_from,valid_to=end))
            unit.revision+=1;validate_tree(db,strict_unit=unit.id if hierarchy_level is not UNSET or parent_changed and parent is not None else None);audit(db,unit,actor_id,'state',before)
        return key

    @staticmethod
    @actor_operation
    def dissolve(db,actor_id,key,revision,end):
        exact_date(end)
        with organization_write(db,actor_id,'dissolve'):
            unit=checked(db,key,revision);before=snapshot(db,unit);period(unit.formed_on,end)
            from app.services.organization_staff import unit_lifecycle_guard
            unit_lifecycle_guard(db,key,end)
            if unit.dissolved_on is not None:raise ValueError('Підрозділ уже розформовано. Повторне формування потребує нового ID.')
            states=Repo.states(db,key)
            if any(s.valid_from>end for s in states):raise ValueError('Спочатку виправте майбутні стани підрозділу.')
            state=state_at(states,key,end)
            if state is None:raise ValueError('Стан підрозділу на дату завершення відсутній.')
            state.valid_to=end;unit.dissolved_on=end
            validate_tree(db);audit(db,unit,actor_id,'dissolve',before)
        return key

    @staticmethod
    @actor_operation
    def annul(db,actor_id,key,revision,why):
        why=reason(why)
        with organization_write(db,actor_id,'annul'):
            unit=checked(db,key,revision);before=snapshot(db,unit)
            from app.services.organization_staff import unit_lifecycle_guard
            unit_lifecycle_guard(db,key)
            active_ids={u.id for u in Repo.units(db) if u.annulled_at is None}
            if any(s.org_unit_id!=key and s.org_unit_id in active_ids and s.primary_parent_id==key for s in Repo.states(db)):
                raise ValueError('Є залежні підрозділи. Спочатку явно виправте їхню історію підпорядкування.')
            if any(s.parent_id==key and s.org_unit_id!=key for s in Repo.operational(db)):
                raise ValueError('Є залежне оперативне підпорядкування.')
            unit.annulled_at=datetime.now(UTC);unit.annulment_reason=why;unit.annulled_by=actor_id
            validate_tree(db);audit(db,unit,actor_id,'annul',before,why)
        return key

    @staticmethod
    @actor_operation
    def reorder(db,actor_id,on,parent_id,ids,*,revisions=None):
        exact_date(on)
        if not isinstance(ids,list) or any(type(key) is not int for key in ids) or len(set(ids))!=len(ids):raise ValueError('Вкажіть унікальні ID підрозділів.')
        with organization_write(db,actor_id,'reorder'):
            units={u.id:u for u in Repo.units(db) if active(u,on)};states=Repo.states(db)
            siblings={key for key in units if state_at(states,key,on).primary_parent_id==parent_id}
            if set(ids)!=siblings:raise ValueError('Сортування дозволено тільки для повного набору дітей одного батьківського підрозділу; воно не змінює підпорядкування.')
            if revisions is not None:
                if not isinstance(revisions,dict):raise ValueError('Потрібні версії записів для сортування.')
                try:stamps={int(key):int(value) for key,value in revisions.items()}
                except (TypeError,ValueError):raise ValueError('Некоректні версії записів сортування.') from None
                if set(stamps)!=siblings or any(units[key].revision!=stamps[key] for key in siblings):raise ValueError('Підрозділи змінилися. Оновіть дерево перед сортуванням.')
            for number,key in enumerate(ids):
                unit=units[key]
                if unit.sort_order!=number:
                    before=snapshot(db,unit);unit.sort_order=number;audit(db,unit,actor_id,'order',before)
        return ids

    @staticmethod
    @actor_operation
    def add_operational(db,actor_id,child_id,parent_id,start,end=None,*,note=None,revision=None):
        period(start,end)
        if child_id==parent_id:raise ValueError('Оперативне підпорядкування самому собі заборонене.')
        if note is not None and (not isinstance(note,str) or len(note)>2000):raise ValueError('Примітка: до 2000 символів.')
        with organization_write(db,actor_id,'operational'):
            child=checked(db,child_id,revision);parent=checked(db,parent_id)
            for unit in (child,parent):
                if start<unit.formed_on or (unit.dissolved_on and (end is None or end>unit.dissolved_on)):raise ValueError('Оперативне підпорядкування виходить за період існування підрозділу.')
            existing=Repo.operational(db)
            if any(s.org_unit_id==child_id and s.parent_id==parent_id and s.valid_from<= (end or date.max) and start<= (s.valid_to or date.max) for s in existing):raise ValueError('Періоди оперативного підпорядкування перетинаються.')
            # Validate operational cycles for every affected interval intersection.
            stack=[(parent_id,start,end or date.max)];visited=set()
            while stack:
                cursor,left,right=stack.pop()
                if cursor==child_id:raise ValueError('Цикл оперативного підпорядкування заборонений.')
                marker=(cursor,left,right)
                if marker in visited:continue
                visited.add(marker)
                for edge in existing:
                    lo=max(left,edge.valid_from);hi=min(right,edge.valid_to or date.max)
                    if edge.org_unit_id==cursor and lo<=hi:stack.append((edge.parent_id,lo,hi))
            before=snapshot(db,child)
            row=Repo.add(db,OperationalSubordination(org_unit_id=child_id,parent_id=parent_id,valid_from=start,valid_to=end,note=note));db.flush()
            child.revision+=1;audit(db,child,actor_id,'operational',before,operational={'id':row.id,'parent_id':parent_id,'valid_from':start.isoformat(),'valid_to':end.isoformat() if end else None});key=row.id
        return key

    @staticmethod
    def tree(db,on):
        exact_date(on);all_units=Repo.units(db);units=[u for u in all_units if active(u,on)];states=Repo.states(db)
        operational=Repo.operational(db)
        result=[];roots=[]
        for unit in units:
            state=state_at(states,unit.id,on)
            if state is None:raise ValueError('Історія організаційної структури неповна.')
            result.append({'id':unit.id,'kind':unit.kind,'hierarchy_level':level_of(unit),'eligible_roster':unit.kind in ROSTER_KINDS,'name':state.name,'parent_id':state.primary_parent_id,
                           'children':[],'operational_parent_ids':[edge.parent_id for edge in operational if edge.org_unit_id==unit.id and edge.valid_from<=on<= (edge.valid_to or date.max)],'sort_order':unit.sort_order,'revision':unit.revision,
                           'formed_on':unit.formed_on.isoformat(),'dissolved_on':unit.dissolved_on.isoformat() if unit.dissolved_on else None})
        for node in result:node['operational_parent_id']=node['operational_parent_ids'][0] if len(node['operational_parent_ids'])==1 else None
        nodes={node['id']:node for node in result}
        for node in result:
            if node['parent_id'] is None:roots.append(node['id'])
            elif node['parent_id'] in nodes:nodes[node['parent_id']]['children'].append(node['id'])
        inactive=[]
        for unit in all_units:
            if active(unit,on):continue
            earlier=[state for state in states if state.org_unit_id==unit.id and state.valid_from<=on]
            all_states=[state for state in states if state.org_unit_id==unit.id]
            state=earlier[-1] if earlier else (all_states[0] if all_states else None)
            inactive.append({'id':unit.id,'kind':unit.kind,'hierarchy_level':level_of(unit),'eligible_roster':unit.kind in ROSTER_KINDS,'name':state.name if state else 'Без історії назви','revision':unit.revision,
                             'formed_on':unit.formed_on.isoformat(),'dissolved_on':unit.dissolved_on.isoformat() if unit.dissolved_on else None,
                             'annulled_at':unit.annulled_at.isoformat() if unit.annulled_at else None,'annulment_reason':unit.annulment_reason})
        return {'units':result,'inactive_units':inactive,'roots':roots,'on':on.isoformat()}

    @staticmethod
    def history(db,key):
        from app.utils.date_utils import format_system_timestamp
        unit=Repo.get(db,key)
        if unit is None:raise ValueError('Підрозділ не існує.')
        payload=snapshot(db,unit);states=payload.pop('states')
        operations=[{'id':row.id,'org_unit_id':row.org_unit_id,'parent_id':row.parent_id,'valid_from':row.valid_from.isoformat(),
                     'valid_to':row.valid_to.isoformat() if row.valid_to else None,'note':row.note,'revision':row.revision}
                    for row in Repo.operational(db) if row.org_unit_id==key]
        audits=[{'id':row.id,'actor_user_id':row.actor_user_id,'occurred_at':format_system_timestamp(row.occurred_at),
                 'operation':row.operation,'before':row.before,'after':row.after,'reason':row.reason} for row in Repo.audits(db,key)]
        return {'unit':payload,'states':states,'operational':operations,'audit':audits}

    @staticmethod
    @actor_operation
    def close_operational(db,actor_id,key,revision,end):
        exact_date(end)
        with organization_write(db,actor_id,'operational'):
            row=Repo.operational_record(db,key)
            if row is None:raise ValueError('Оперативне підпорядкування не існує.')
            if row.revision!=revision:raise ValueError('Запис змінився. Оновіть дані.')
            if end<row.valid_from or (row.valid_to is not None and end>row.valid_to):raise ValueError('Завершення не може подовжувати або інвертувати період.')
            child=checked(db,row.org_unit_id);before=snapshot(db,child);previous=row.valid_to
            row.valid_to=end;child.revision+=1
            validate_tree(db);audit(db,child,actor_id,'operational',before,operational={'id':row.id,'previous_valid_to':previous.isoformat() if previous else None,'valid_to':end.isoformat()})
        return key


@actor_operation
def create_locked(db,actor_id,kind,name,formed_on,*,parent_id=None,dissolved_on=None,hierarchy_level=None,validate=True):
    """Participate in an existing write unit; caller commits the full import atomically."""
    if not db.info.get('project2_write'):raise ValueError('create_locked потребує зовнішньої write unit.')
    Repo.lock(db);authorize(db,actor_id,'create');period(formed_on,dissolved_on);normalized=normalize(name)
    if kind not in KINDS:raise ValueError('Невідомий вид підрозділу.')
    hierarchy_level=explicit_level(kind,hierarchy_level)
    if parent_id is not None:checked(db,parent_id)
    from app.services.access_views import scoped
    e=scoped(db)
    if e and not e.allowed('organization','edit',unit_id=parent_id):raise PermissionError('Недостатньо прав на створення підрозділу в цій області.')
    db.info['access_new_unit_parent']=parent_id
    unit=Repo.add(db,OrgUnit(kind=kind,hierarchy_level=hierarchy_level,formed_on=formed_on,dissolved_on=dissolved_on));db.flush()
    if parent_id is not None:hierarchy_edge(unit,checked(db,parent_id))
    Repo.add(db,OrgUnitState(org_unit_id=unit.id,name=name.strip(),normalized_name=normalized,primary_parent_id=parent_id,valid_from=formed_on,valid_to=dissolved_on))
    if validate:validate_tree(db)
    audit(db,unit,actor_id,'create',{})
    return unit.id

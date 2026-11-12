"""Scoped, previewed staffing changes and compensating withdrawal, never deletion."""
from app.services.access_context import actor_operation
from datetime import date,datetime,UTC,timedelta
import hashlib,json,secrets
from app.models import Position,StaffVersion,StaffStructure,PersonAssignment
from app.models.organization import OrgUnit
from app.models.organization_staff import OrgStaffImport,OrgStaffImportRow,OrgReassignment,OrgCoverage
from app.repositories.organization_import_repository import OrganizationImportRepository as Repo
from app.services import organization,organization_staff as staff
from app.services.organization_excel import read_positions
from app.validators.position_validator import POSITION_ATTRIBUTES,validate_position
from app.services.staff_service import period,version_conflict,StaffService

MODES=frozenset({'add','official','correct','replace'})

def _iso(value):return value.isoformat() if value else None

def _position(row):
    return {**{key:getattr(row,key) for key in POSITION_ATTRIBUTES},'id':row.position_id,'revision':row.revision,
            'staff_version_id':row.staff_version_id,'org_unit_id':row.org_unit_id,'managed_unit_id':row.managed_unit_id,
            'valid_from':_iso(row.valid_from),'valid_to':_iso(row.valid_to)}

def _assignment(row):
    return {'id':row.id,'person_id':row.person_id,'position_id':row.staff_position_id,'revision':row.revision,
            'assigned_from':_iso(row.assigned_from),'assigned_to':_iso(row.assigned_to),
            'assignment_order_number':row.assignment_order_number,'assignment_order_date':_iso(row.assignment_order_date),
            'release_order_number':row.release_order_number,'release_order_date':_iso(row.release_order_date),
            'completion_reason':row.completion_reason,'completion_note':row.completion_note}

def _tree_signature(nodes,ids,exclude=()):
    fields=('id','kind','hierarchy_level','name','parent_id','revision','formed_on','dissolved_on')
    data=[{key:node.get(key) for key in fields} for node in nodes if node['id'] in ids and node['id'] not in exclude]
    return hashlib.sha256(json.dumps(sorted(data,key=lambda n:n['id']),ensure_ascii=False,sort_keys=True).encode()).hexdigest()

def _resolve(nodes,scope_id,path):
    current=scope_id
    for key in path[1:]:
        children=[node for node in nodes if node['parent_id']==current and organization.normalize(node['name'])==key]
        if len(children)>1:return None,'Неоднозначний шлях підрозділу; потрібне явне зіставлення.'
        if not children:return None,None
        current=children[0]['id']
    return current,None

def _path_hierarchy(nodes,scope_id,item):
    from types import SimpleNamespace
    current=next(node for node in nodes if node['id']==scope_id)
    for i,key in enumerate(item['path_keys'][1:]):
        existing=next((node for node in nodes if node['parent_id']==current.get('id') and organization.normalize(node['name'])==key),None) if current.get('id') else None
        spec=(item.get('unit_specs') or [{}]*len(item['path_keys']))[i]
        if existing:
            if spec.get('kind') and spec['kind']!=existing['kind']:raise ValueError('Тип існуючого підрозділу не можна змінити через імпорт.')
            raw=spec.get('hierarchy_level')
            if raw is not None and organization.explicit_level(existing['kind'],raw)!=existing['hierarchy_level']:raise ValueError('Рівень існуючого підрозділу не змінюється через імпорт.')
            child=existing
        else:
            kind=spec.get('kind')
            if kind not in organization.KINDS:raise ValueError('Для нового підрозділу вкажіть child_N_kind та для other — child_N_level або спочатку створіть підрозділ у дереві.')
            raw=spec.get('hierarchy_level')
            if type(raw) is float and raw.is_integer():raw=int(raw)
            level=organization.explicit_level(kind,raw)
            child={'kind':kind,'hierarchy_level':level,'id':None}
        organization.hierarchy_edge(SimpleNamespace(**child),SimpleNamespace(**current))
        current=child

def _source(db,scope_id,on,mode):
    current=staff.snapshot(db,scope_id,on)
    source=current
    source_on=on
    if mode=='official' and not current['owner_positions'] and on>date.min:
        try:
            previous=staff.snapshot(db,scope_id,on-timedelta(days=1))
            if previous['owner']['id']==current['owner']['id']:
                source={**current,'positions':[p for p in previous['positions'] if p.org_unit_id in current['unit_ids']],'owner_positions':[p for p in previous['owner_positions'] if p.org_unit_id in current['owner_unit_ids']]}
                source_on=on-timedelta(days=1)
        except ValueError:pass
    return current,source,source_on

def _target_version(db,current,source,on,version_id,mode):
    if mode=='official':return None
    versions={p.staff_version_id for p in source['positions']}
    if not versions:
        versions={c.staff_version_id for c in Repo.coverages(db,current['unit_ids']) if c.valid_from<=on and (c.valid_to is None or c.valid_to>=on)}
    if version_id is None:
        if len(versions)!=1:raise ValueError('Вкажіть однозначну чинну версію; для першої штатки оберіть нову офіційну версію.')
        version_id=next(iter(versions))
    version=Repo.get(db,StaffVersion,int(version_id))
    if not version or version.id not in versions or not version.valid_from<=on<= (version.valid_to or date.max):
        raise ValueError('Вибрана версія не є чинним джерелом у зазначеній області.')
    structure=Repo.get(db,StaffStructure,version.staff_structure_id)
    if structure.org_unit_id is None or Repo.unmapped(db,structure.id):raise ValueError('Спочатку явно зіставте legacy-структуру та всі її посади з підрозділами. Автоматичного зіставлення немає.')
    return version

@actor_operation
def preview(db,actor,source,scope_id,mode,on,end=None,name='',version_id=None):
    organization.authorize(db,actor,'import',scope_id)
    if mode not in MODES:raise ValueError('Невідомий режим імпорту.')
    period(on,end)
    if mode=='official' and (not isinstance(name,str) or not name.strip() or len(name.strip())>150):raise ValueError('Назва офіційної версії: 1–150 символів.')
    current,composition,source_on=_source(db,scope_id,on,mode)
    staff.require_complete_mapping(db,scope_id,source_on)
    from app.services import access
    e=access.Access(db,actor)
    if not e.allowed('organization','read',unit_id=current['owner']['id'] if mode=='official' else scope_id):raise PermissionError('Вихідна область штатки недоступна.')
    if mode=='official' and not e.allowed('organization','import',unit_id=current['owner']['id']):raise PermissionError('Нова версія змінює повну область власника. Потрібен дозвіл імпорту на всю роту або вищий підрозділ.')
    if mode!='official':composition={**composition,'owner_positions':composition['positions']}
    parsed=read_positions(source,current['selected']['name'])
    version=_target_version(db,current,composition,on,version_id,mode)
    owner_structure=Repo.structure(db,current['owner']['id'])
    if owner_structure and Repo.unmapped(db,owner_structure.id):raise ValueError('У структурі є незіставлені legacy-посади; спочатку виконайте явне зіставлення.')
    if mode=='official' and owner_structure:
        version_conflict(db,owner_structure.id,on,end)
    selected={p.position_id:p for p in composition['positions']}
    by_number={}
    for p in composition['owner_positions']:by_number.setdefault(p.position_number,[]).append(p)
    dependencies=Repo.assignments(db,[p.position_id for p in composition['owner_positions']])
    from app.services.person_picker import person_options
    names={person['id']:person['label'] for person in person_options(db,on)} if dependencies else {}
    assignment_data=[{**_assignment(a),'person_label':names.get(a.person_id,f'Людина ID {a.person_id}')} for a in dependencies]
    rows=[]
    for item in parsed['rows']:
        candidate={**item,'status':'pending','current_id':None,'current_revision':None,'unit_id':None,'diff':{},'dependencies':[]}
        unit_id,issue=_resolve(current['nodes'],scope_id,item['path_keys']);candidate['unit_id']=unit_id
        issues=list(item.get('errors',[]))
        if issue:issues.append(issue)
        try:_path_hierarchy(current['nodes'],scope_id,item)
        except ValueError as error:issues.append(str(error))
        if not item.get('position_valid',True):
            candidate['status']='conflict';candidate['issues']=issues;rows.append(candidate);continue
        matches=by_number.get(item['position']['position_number'],[])
        if len(matches)>1 and unit_id is not None:
            local=[p for p in matches if p.org_unit_id==unit_id]
            if len(local)==1:matches=local
        if len(matches)>1:issues.append('Номер посади неоднозначний у складі власника версії.')
        elif matches:
            existing=matches[0];candidate['current_id']=existing.position_id;candidate['current_revision']=existing.revision
            if existing.position_id not in selected:issues.append('Номер зайнятий посадою за межами вибраного підрозділу.')
            elif mode!='official' and (unit_id is None or existing.org_unit_id!=unit_id):issues.append('Історична належність посади відрізняється; потрібна нова офіційна версія, а не зміна історії.')
            candidate['diff']={key:{'before':getattr(existing,key),'after':value} for key,value in item['position'].items() if getattr(existing,key)!=value}
            if mode=='official' and existing.org_unit_id!=unit_id:candidate['diff']['org_unit_id']={'before':existing.org_unit_id,'after':unit_id or 'Новий підрозділ за шляхом'}
            candidate['dependencies']=[a for a in assignment_data if a['position_id']==existing.position_id]
            if not issues and not candidate['diff']:candidate['status']='unchanged'
            elif mode=='add' and candidate['diff']:issues.append('Номер уже існує з іншими реквізитами; оберіть контрольоване виправлення або заміну.')
        elif mode=='correct':issues.append('Посада для точкового виправлення відсутня; використайте режим доповнення.')
        if issues:candidate['status']='conflict'
        candidate['issues']=issues
        rows.append(candidate)
    definitions={}
    for row in rows:
        for index,spec in enumerate(row.get('unit_specs',[])):
            if not spec.get('kind'):continue
            path=tuple(row['path_keys'][:index+2]);signature=(spec['kind'],spec.get('hierarchy_level'))
            previous=definitions.setdefault(path,(set(),[]));previous[0].add(signature);previous[1].append(row)
    for signatures,affected_rows in definitions.values():
        if len(signatures)>1:
            for affected in affected_rows:
                affected['status']='conflict'
                affected['issues'].append('Різні типи або рівні одного нового підрозділу в рядках Excel.')
    return {'identity_key':secrets.token_hex(32),'scope_id':scope_id,'owner_id':current['owner']['id'],'mode':mode,
            'on':on.isoformat(),'end':_iso(end),'source_on':source_on.isoformat(),'name':name.strip(),'version_id':version.id if version else None,
            'tree_signature':_tree_signature(current['nodes'],current['owner_unit_ids']),
            'source_positions':[_position(p) for p in composition['owner_positions']],
            'scope_position_ids':sorted(selected),'rows':rows,'errors':parsed['errors'],'warnings':parsed['warnings'],
            'dependencies':[a for a in assignment_data if a['position_id'] in selected],
            'owner_unit_ids':current['owner_unit_ids']}

@actor_operation
def _receipt(db,actor,prepared):
    receipt=Repo.receipt(db,prepared['identity_key'])
    if receipt:
        if receipt.withdrawn_at:raise ValueError('Цей імпорт відкликано; повторне підтвердження заборонене.')
        if receipt.snapshot!=prepared:raise ValueError('Підготовлені дані не відповідають квитанції імпорту.')
        return receipt
    receipt=Repo.add(db,OrgStaffImport(identity_key=prepared['identity_key'],scope_unit_id=prepared['scope_id'],owner_unit_id=prepared['owner_id'],
        mode=prepared['mode'],effective_on=date.fromisoformat(prepared['on']),valid_to=date.fromisoformat(prepared['end']) if prepared['end'] else None,
        actor_id=actor,snapshot=prepared,effects={}))
    db.flush()
    for item in prepared['rows']:
        Repo.add(db,OrgStaffImportRow(import_id=receipt.id,row_number=item['row_number'],payload=item,
            status='conflict' if item['status']=='conflict' else 'pending',issue='; '.join(item.get('issues',[])) or None))
    db.flush();return receipt

@actor_operation
def _path_unit(db,actor,prepared,item,current,effects,on):
    nodes=current['nodes'];current_id=prepared['scope_id'];created=list(effects.get('created_unit_ids',[]))
    for index,(display,key) in enumerate(zip(item['path'][1:],item['path_keys'][1:])):
        choices=[node for node in nodes if node['parent_id']==current_id and organization.normalize(node['name'])==key]
        if len(choices)>1:raise ValueError('Неоднозначне підпорядкування; повторіть явне зіставлення.')
        if choices:
            spec=item.get('unit_specs',[{}]*len(item['path']))[index]
            if spec.get('kind') and spec['kind']!=choices[0]['kind']:raise ValueError('Тип підрозділу змінився після preview; повторіть перевірку.')
            current_id=choices[0]['id'];continue
        spec=item['unit_specs'][index]
        raw=spec.get('hierarchy_level');raw=int(raw) if type(raw) is float and raw.is_integer() else raw
        current_id=organization.create_locked(db,actor,spec.get('kind'),display,on,parent_id=current_id,hierarchy_level=raw,validate=False)
        created.append(current_id)
        # Refresh the lightweight effective tree so deeper path nodes use real parent IDs.
        nodes[:]=organization.OrganizationService.tree(db,on)['units']
    effects['created_unit_ids']=created
    return current_id

def _check_source(db,prepared,receipt):
    touched={row.before['id']:row for row in Repo.rows(db,receipt.id) if row.before and row.status=='accepted'}
    for before in prepared['source_positions']:
        current=Repo.get(db,Position,before['id'])
        # Rows already corrected/replaced by this receipt have their own after revision.
        if before['id'] in touched:continue
        if not current or current.revision!=before['revision'] or current.annulled_at:raise ValueError('Склад штатки змінився після preview. Перевірте файл повторно.')

def _new_position(db,version,unit_id,fields,on,end,managed=None):
    row=Repo.add(db,Position(staff_version_id=version.id,org_unit_id=unit_id,managed_unit_id=managed,valid_from=on,valid_to=end,**validate_position(fields)))
    db.flush();return row

@actor_operation
def _official(db,actor,prepared,receipt,current,effects,on,end,remove_ids,overrides):
    if receipt.staff_version_id:return Repo.get(db,StaffVersion,receipt.staff_version_id)
    structure=staff.ensure_structure(db,prepared['owner_id'])
    version_conflict(db,structure.id,on,end)
    # Independent child sources can reuse numbers. Combining them in one owner
    # snapshot still requires the ordinary per-version uniqueness rule.
    numbers={}
    for before in prepared['source_positions']:
        if before['id'] not in remove_ids and before['id'] not in overrides:
            numbers.setdefault(before['position_number'],[]).append(before['id'])
    for row in Repo.rows(db,receipt.id):
        if row.row_number in effects.get('selected_rows',[]) and row.payload.get('current_id') in overrides:
            numbers.setdefault(row.payload['position']['position_number'],[]).append(row.payload['current_id'])
    duplicates={number:ids for number,ids in numbers.items() if len(ids)>1}
    if duplicates:raise ValueError('Джерела мають однакові номери посад: '+', '.join(str(n) for n in sorted(duplicates))+'. Явно виберіть вилучення зайвих посад або узгодьте їхні офіційні номери.')
    version=Repo.add(db,StaffVersion(staff_structure_id=structure.id,name=prepared['name'],valid_from=on,valid_to=end,import_key=prepared['identity_key']))
    db.flush();clone_map={};created=[]
    for before in prepared['source_positions']:
        if before['id'] in remove_ids or before['id'] in overrides:continue
        old=Repo.get(db,Position,before['id']);finish=min([value for value in (end,old.valid_to) if value is not None],default=None)
        row=_new_position(db,version,old.org_unit_id,before,on,finish,old.managed_unit_id)
        clone_map[str(old.position_id)]={'id':row.position_id,'revision':row.revision};created.append(row.position_id)
    effects['version_created']=True;effects['clone_map']=clone_map;effects['created_position_ids']=created
    receipt.staff_version_id=version.id
    staff.replace_coverage(db,actor,version,current['owner_unit_ids'],on,end)
    db.flush();effects['created_coverage_ids']=[c.id for c in Repo.coverages(db,current['owner_unit_ids']) if c.staff_version_id==version.id]
    return version

@actor_operation
def confirm(db,actor,prepared,selected_rows,*,reason=None,replace_ids=(),confirm_removal=False):
    organization.authorize(db,actor,'import',prepared['scope_id'])
    organization.authorize(db,actor,'view',prepared['scope_id'])
    if prepared['mode']=='official':organization.authorize(db,actor,'import',prepared['owner_id'])
    selected=set(selected_rows)
    mode=prepared['mode'];on=date.fromisoformat(prepared['on']);end=date.fromisoformat(prepared['end']) if prepared['end'] else None
    if selected and mode in ('correct','replace'):
        reason=organization.reason(reason)
        if not confirm_removal:raise ValueError('Підтвердьте виправлення та збереження/анулювання залежних призначень.')
    remove_ids={int(key) for key in replace_ids}
    if remove_ids and not confirm_removal:raise ValueError('Вилучення посад потребує окремого підтвердження.')
    with organization.organization_write(db,actor,'import'):
        current=staff.snapshot(db,prepared['scope_id'],on)
        receipt=_receipt(db,actor,prepared);effects=dict(receipt.effects or {})
        if receipt.staff_version_id is None and prepared['version_id']:
            receipt.staff_version_id=prepared['version_id']
        rows={row.row_number:row for row in Repo.rows(db,receipt.id)}
        if not selected<=set(rows):raise ValueError('Невідомі номери рядків підтвердження.')
        if any(rows[key].status=='conflict' for key in selected):raise ValueError('Спочатку розв’яжіть конфлікти вибраних рядків; безконфліктні можна підтвердити окремо.')
        todo=[rows[key] for key in sorted(selected) if rows[key].status=='pending']
        if not todo:
            if not selected:
                staff.audit(db,actor,prepared['scope_id'],'import',after={'import_id':receipt.id,'staged_only':True,'rows_saved':len(rows)})
            return receipt.id
        signature=_tree_signature(current['nodes'],current['owner_unit_ids'],effects.get('created_unit_ids',[]))
        if signature!=prepared['tree_signature']:raise ValueError('Організаційне дерево змінилося після preview.')
        for key,expected in effects.get('created_position_revisions',{}).items():
            candidate=Repo.get(db,Position,int(key))
            superseded=int(key) in effects.get('superseded_clone_ids',[])
            if candidate is None or candidate.revision!=expected or bool(candidate.annulled_at)!=superseded:raise ValueError('Посади цього імпорту вже змінено. Потрібен новий preview.')
        for key,expected in effects.get('created_unit_revisions',{}).items():
            candidate=Repo.get(db,OrgUnit,int(key))
            if candidate is None or candidate.revision!=expected or candidate.annulled_at:raise ValueError('Створені підрозділи вже змінено. Потрібен новий preview.')
        _check_source(db,prepared,receipt)
        if not remove_ids<=set(prepared['scope_position_ids']):raise ValueError('Заміна/вилучення дозволена лише для явно вибраних посад цієї області.')
        if mode=='replace' and not remove_ids:raise ValueError('Для повної заміни явно виберіть помилкові посади.')
        if mode=='replace' and effects.get('replaced_position_ids') and remove_ids!=set(effects['replaced_position_ids']):
            raise ValueError('Область уже підтвердженої заміни не змінюється; для іншої області потрібен новий preview.')
        effects['selected_rows']=[row.row_number for row in todo]
        version=_official(db,actor,prepared,receipt,current,effects,on,end,remove_ids,{row.payload['current_id'] for row in todo if row.payload.get('current_id')}) if mode=='official' else Repo.get(db,StaffVersion,prepared['version_id'])
        if receipt.staff_version_id is None:receipt.staff_version_id=version.id
        if mode=='replace' and not effects.get('replaced_position_ids'):
            expected={(a['id'],a['revision']) for a in prepared['dependencies'] if a['position_id'] in remove_ids}
            actual={(a.id,a.revision) for a in Repo.assignments(db,remove_ids)}
            if actual!=expected:raise ValueError('Залежні призначення змінилися після preview. Перегляньте людей і періоди повторно.')
            for key in sorted(remove_ids):
                old=Repo.get(db,Position,key)
                if old.staff_version_id!=version.id or old.annulled_at:raise ValueError('Посада вже змінена або належить іншій версії.')
                for assignment in Repo.assignments(db,[key]):
                    StaffService.annul_assignment_locked(db,assignment.id,assignment.revision,reason,actor_id=actor)
                    Repo.add(db,OrgReassignment(import_id=receipt.id,assignment_id=assignment.id))
                old.annulled_at=datetime.now(UTC);old.annulment_reason=reason;old.annulled_by=actor
                staff.audit(db,actor,old.org_unit_id,'position_annul',before=_position(old),after={'position_id':key,'annulled':True},reason=reason)
            db.flush();effects['replaced_position_ids']=sorted(remove_ids)
        for row in todo:
            item=row.payload
            if item.get('duplicate_of'):
                source=rows.get(item['duplicate_of'])
                if source is None or source.status not in ('accepted','unchanged'):raise ValueError('Спочатку підтвердьте основний рядок точного дубліката.')
                row.status='unchanged';row.position_id=source.position_id;row.after_revision=source.after_revision;continue
            unit_id=_path_unit(db,actor,prepared,item,current,effects,on)
            target=None
            if mode=='official' and item['current_id']:
                target=Repo.get(db,Position,effects['clone_map'].get(str(item['current_id']),{}).get('id')) if str(item['current_id']) in effects['clone_map'] else None
            elif item['current_id'] and mode!='replace':target=Repo.get(db,Position,item['current_id'])
            if mode=='official' and target and target.org_unit_id!=unit_id:
                # A later partial confirmation may move a previously copied,
                # vacant position. Preserve that physical row's organization.
                if Repo.assignments(db,[target.position_id],include_annulled=True):raise ValueError('Скопійована посада вже має історію призначень; потрібне окреме контрольоване виправлення.')
                before=_position(target)
                target.annulled_at=datetime.now(UTC);target.annulment_reason=f'Підтвердження шляху рядка {row.row_number} імпорту {receipt.id}';target.annulled_by=actor
                effects['superseded_clone_ids']=[*effects.get('superseded_clone_ids',[]),target.position_id]
                db.flush();staff.audit(db,actor,target.org_unit_id,'position_annul',before=before,after={'position_id':target.position_id,'annulled':True},reason=target.annulment_reason)
                target=None
            if target:
                expected=effects.get('clone_map',{}).get(str(item['current_id']),{}).get('revision',item['current_revision'])
                if target.revision!=expected:raise ValueError('Посада змінилася після preview; потрібне нове підтвердження.')
                if target.org_unit_id!=unit_id:raise ValueError('Історична належність посади не змінюється.')
                row.before=_position(target)
                if mode=='official' and Repo.assignments(db,[target.position_id]):raise ValueError('Нова посада вже має призначення; виправляйте її окремо.')
                for field,value in validate_position(item['position']).items():setattr(target,field,value)
                db.flush();row.status='unchanged' if not item['diff'] else 'accepted'
                if mode=='correct' and row.status=='accepted':staff.audit(db,actor,unit_id,'position',before=row.before,after=_position(target),reason=reason)
            else:
                existing=[p for p in Repo.positions(db,version.id) if p.position_number==item['position']['position_number']]
                if existing:raise ValueError('Номер посади зайнятий; потрібне ручне вирішення конфлікту.')
                effective_start=on
                effective_end=min([value for value in (end,version.valid_to) if value is not None],default=None)
                if mode=='replace' and item.get('current_id') in effects.get('replaced_position_ids',[]):
                    original=Repo.get(db,Position,item['current_id'])
                    effective_start=original.valid_from
                    effective_end=original.valid_to
                managed=None
                if mode=='official' and item.get('current_id'):managed=Repo.get(db,Position,item['current_id']).managed_unit_id
                target=_new_position(db,version,unit_id,item['position'],effective_start,effective_end,managed)
                effects['created_position_ids']=[*effects.get('created_position_ids',[]),target.position_id];row.status='accepted'
                if mode=='official' and item.get('current_id'):effects['clone_map'][str(item['current_id'])]={'id':target.position_id,'revision':target.revision}
            row.position_id=target.position_id;row.after_revision=target.revision
            if mode=='replace':
                for queue in Repo.reassignment_rows(db,receipt.id):
                    assignment=Repo.get(db,PersonAssignment,queue.assignment_id);old=Repo.get(db,Position,assignment.staff_position_id)
                    if old.position_number==target.position_number:queue.replacement_position_id=target.position_id
            coverages=[c for c in Repo.coverages(db,[unit_id]) if c.valid_from<=on<= (c.valid_to or date.max)]
            if any(c.staff_version_id!=version.id for c in coverages):raise ValueError('Підрозділ має інше незалежне джерело; режим доповнення його не замінює.')
            before_ids={c.id for c in coverages}
            staff.replace_coverage(db,actor,version,[unit_id],on,end or version.valid_to)
            effects['created_coverage_ids']=list(dict.fromkeys([*effects.get('created_coverage_ids',[]),*[c.id for c in Repo.coverages(db,[unit_id]) if c.id not in before_ids and c.staff_version_id==version.id]]))
        organization.validate_tree(db)
        db.flush()
        effects['created_position_revisions']={str(key):Repo.get(db,Position,key).revision for key in effects.get('created_position_ids',[])}
        effects['created_unit_revisions']={str(key):Repo.get(db,OrgUnit,key).revision for key in effects.get('created_unit_ids',[])}
        effects['created_coverage_revisions']={str(key):Repo.get(db,OrgCoverage,key).revision for key in effects.get('created_coverage_ids',[])}
        effects['version_revision']=version.revision
        receipt.effects=effects
        staff.audit(db,actor,prepared['scope_id'],'import',after={'import_id':receipt.id,'mode':mode,'rows':[row.row_number for row in todo],'version_id':version.id},reason=reason)
        key=receipt.id
    return key

@actor_operation
def withdrawal(db,actor,receipt_id,reason):
    reason=organization.reason(reason)
    with organization.organization_write(db,actor,'withdraw'):
        receipt=Repo.get(db,OrgStaffImport,receipt_id)
        if receipt is None:raise ValueError('Квитанція імпорту відсутня.')
        if receipt.withdrawn_at:raise ValueError('Імпорт уже відкликано.')
        from app.services.access import require
        require(db,'organization','edit',unit_id=receipt.scope_unit_id,actor_id=actor)
        effects=receipt.effects or {};created=effects.get('created_position_ids',[])
        if Repo.assignments(db,created,include_annulled=True):raise ValueError('Імпорт має подальші призначення; спочатку явно опрацюйте всі залежності.')
        rows=Repo.rows(db,receipt.id)
        dependent=Repo.dependent_receipts(db,receipt.id,created+[r.position_id for r in rows if r.before],effects.get('created_unit_ids',[]))
        if dependent:raise ValueError('Від імпорту залежать інші квитанції: '+', '.join(map(str,dependent))+'. Спочатку явно опрацюйте залежні імпорти.')
        version=Repo.get(db,StaffVersion,receipt.staff_version_id) if receipt.staff_version_id else None
        if version and version.revision!=effects.get('version_revision',version.revision):raise ValueError('Версію змінено після імпорту; потрібен ручний аналіз залежностей.')
        if effects.get('version_created') and any(p.position_id not in created for p in Repo.positions(db,receipt.staff_version_id)):
            raise ValueError('Версія має посади з інших операцій. Спочатку опрацюйте залежні імпорти.')
        if effects.get('version_created') and any(c.staff_version_id==receipt.staff_version_id and c.id not in effects.get('created_coverage_ids',[]) for c in Repo.coverages(db,receipt.snapshot['owner_unit_ids'])):
            raise ValueError('Версія має джерела чинності з інших операцій. Спочатку опрацюйте залежні імпорти.')
        for key,revision in effects.get('created_position_revisions',{}).items():
            position=Repo.get(db,Position,int(key))
            if not position or position.revision!=revision:raise ValueError('Створені посади змінено після імпорту.')
        for key,revision in effects.get('created_coverage_revisions',{}).items():
            coverage=Repo.get(db,OrgCoverage,int(key))
            if not coverage or coverage.revision!=revision or coverage.annulled_at:raise ValueError('Джерела чинності змінено після імпорту.')
        for row in rows:
            if row.position_id is None or row.status not in ('accepted','unchanged'):continue
            position=Repo.get(db,Position,row.position_id)
            if position is None or position.revision!=row.after_revision:raise ValueError('Посади змінено після імпорту; автоматичне відкликання заборонене.')
        for row in rows:
            if row.before and row.position_id not in created and row.status=='accepted':
                position=Repo.get(db,Position,row.position_id)
                for field in POSITION_ATTRIBUTES:setattr(position,field,row.before[field])
        for key in created:
            position=Repo.get(db,Position,key)
            if position.annulled_at:
                if key in effects.get('superseded_clone_ids',[]):continue
                raise ValueError('Посаду вже анульовано окремою операцією.')
            position.annulled_at=datetime.now(UTC);position.annulment_reason=reason;position.annulled_by=actor
        for key in effects.get('created_coverage_ids',[]):
            coverage=Repo.get(db,OrgCoverage,key)
            if coverage and not coverage.annulled_at:
                coverage.annulled_at=datetime.now(UTC);coverage.annulment_reason=reason
        db.flush()
        if effects.get('version_created'):
            version.annulled_at=datetime.now(UTC);version.annulment_reason=reason;version.annulled_by=actor
        receipt.withdrawn_at=datetime.now(UTC);receipt.withdrawal_reason=reason
        staff.audit(db,actor,receipt.scope_unit_id,'withdraw',after={'import_id':receipt.id,'annulled_position_ids':created,'assignments_restored':False},reason=reason)
    return receipt_id


@actor_operation
def receipt_data(db,actor,key):
    organization.authorize(db,actor,'view')
    receipt=Repo.get(db,OrgStaffImport,key)
    if receipt is None:raise ValueError('Квитанція імпорту відсутня.')
    from app.services.access import require
    require(db,'organization',unit_id=receipt.scope_unit_id,actor_id=actor)
    for p in receipt.snapshot.get('source_positions',[]):require(db,'organization',unit_id=p['org_unit_id'],actor_id=actor)
    public=preview_data(db,actor,receipt.snapshot)
    rows={row['row_number']:row for row in public['rows']}
    return {'id':receipt.id,'revision':receipt.revision,'mode':receipt.mode,'version_id':receipt.staff_version_id,
        'scope':receipt.scope_unit_id,'snapshot':public,'withdrawn_at':_iso(receipt.withdrawn_at),'withdrawal_reason':receipt.withdrawal_reason,
        'rows':[{'row_number':r.row_number,'revision':r.revision,'status':r.status,'issue':r.issue,'position_id':r.position_id,'payload':rows.get(r.row_number,{})} for r in Repo.rows(db,key)]}


@actor_operation
def preview_data(db,actor,prepared):
    """Project dependency details without changing the private confirmation snapshot."""
    from copy import deepcopy
    from app.services.access import Access
    e=Access(db,actor);public=deepcopy(prepared)
    if e.user.role=='admin':return public
    def safe(rows):
        return [r if e.allowed('service',person_id=r['person_id']) and e.allowed('service',position_id=r['position_id']) else
                {'restricted':True,'id':'—','person_label':'Реквізити призначення недоступні','position_id':r['position_id'],'assigned_from':None,'assigned_to':None} for r in rows]
    public['dependencies']=safe(public.get('dependencies',[]))
    for row in public.get('rows',[]):row['dependencies']=safe(row.get('dependencies',[]))
    return public


@actor_operation
def receipt_for_confirmation(db,actor,key):
    receipt=Repo.get(db,OrgStaffImport,key)
    if receipt is None:raise ValueError('Квитанція імпорту відсутня.')
    organization.authorize(db,actor,'import',receipt.scope_unit_id)
    return receipt.snapshot


@actor_operation
def resolve_conflict(db,actor,key,row_number,decision,reason,revision):
    reason=organization.reason(reason)
    if decision not in ('keep','correct'):raise ValueError('Виберіть залишити поточні дані/пропустити або явно виправити реквізити.')
    with organization.organization_write(db,actor,'import'):
        receipt=Repo.get(db,OrgStaffImport,key)
        if receipt is None or receipt.withdrawn_at:raise ValueError('Імпорт недоступний або відкликаний.')
        organization.authorize(db,actor,'import',receipt.scope_unit_id)
        row=next((r for r in Repo.rows(db,key) if r.row_number==row_number),None)
        if row is None or row.status!='conflict' or row.revision!=int(revision):raise ValueError('Конфлікт уже змінений. Оновіть квитанцію.')
        current=Repo.get(db,Position,row.payload.get('current_id')) if row.payload.get('current_id') else None
        if decision=='correct':
            if not current or current.annulled_at or current.org_unit_id!=row.payload.get('unit_id') or current.staff_version_id!=receipt.staff_version_id:
                raise ValueError('Належність посади або версія відрізняється. Підготуйте окремий контрольований імпорт заміни.')
            if current.revision!=row.payload.get('current_revision'):raise ValueError('Посаду змінено після preview. Потрібен новий перегляд відмінностей.')
            if row.payload.get('errors'):raise ValueError('Спочатку виправте структуру чи дублікати Excel в новому preview.')
            row.before=_position(current)
            for field,value in validate_position(row.payload['position']).items():setattr(current,field,value)
            db.flush();row.status='accepted';row.position_id=current.position_id;row.after_revision=current.revision
            staff.audit(db,actor,current.org_unit_id,'position',before=row.before,after=_position(current),reason=reason)
        else:
            row.status='unchanged';row.position_id=current.position_id if current else None;row.after_revision=current.revision if current else None
        row.issue=('Явно збережено поточні дані / пропущено' if decision=='keep' else 'Конфлікт явно виправлено')+': '+reason
        staff.audit(db,actor,receipt.scope_unit_id,'import',after={'import_id':key,'row':row_number,'decision':decision},reason=reason)
    return key

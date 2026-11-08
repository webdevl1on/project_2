"""Effective staffing sources, explicit legacy mapping and period eligibility."""
from datetime import date,datetime,UTC,timedelta
from app.models import StaffStructure,StaffVersion,Position,PersonAssignment
from app.models.organization import OrgUnit,OrgAudit,ROSTER_KINDS
from app.models.organization_staff import OrgCoverage
from app.repositories.organization_staff_repository import OrganizationStaffRepository as Repo
from app.services.organization import OrganizationService,organization_write,checked as org_checked,authorize
from app.services.staff_service import checked,period


def audit(db,actor_id,org_unit_id,operation,before=None,after=None,reason=None):
    db.add(OrgAudit(org_unit_id=org_unit_id,actor_user_id=actor_id,operation=operation,before=before or {},after=after or {},reason=reason));db.flush()


def snapshot(db,scope_id,on):
    tree=OrganizationService.tree(db,on);nodes={node['id']:node for node in tree['units']}
    if scope_id not in nodes:raise ValueError('Підрозділ не діє на обрану дату або анульований.')
    selected=nodes[scope_id];owner=selected
    while owner['kind'] not in ROSTER_KINDS:
        parent=owner.get('parent_id')
        if parent not in nodes:raise ValueError('Для версії потрібен явно визначений підрозділ рівня роти або вище.')
        owner=nodes[parent]
    def subtree(root):
        ids=[];stack=[root]
        while stack:
            key=stack.pop();ids.append(key);stack.extend(nodes[key].get('children',[]))
        return ids
    ids=subtree(scope_id);owner_ids=subtree(owner['id'])
    return {'tree':tree,'nodes':list(nodes.values()),'selected':selected,'owner':owner,'unit_ids':ids,'owner_unit_ids':owner_ids,
            'positions':Repo.positions(db,ids,on),'owner_positions':Repo.positions(db,owner_ids,on)}


def ensure_structure(db,owner_id):
    unit=org_checked(db,owner_id)
    if unit.kind not in ROSTER_KINDS:raise ValueError('Власна історія версій дозволена лише роті та вищим підрозділам.')
    structure=Repo.structure(db,owner_id)
    if structure is None:
        structure=StaffStructure(org_unit_id=owner_id,code=f'org-{owner_id}',name=f'Штат підрозділу ID {owner_id}');db.add(structure);db.flush()
    return structure


def assert_position_period(db,position,start,end):
    period(start,end)
    version=checked(db,StaffVersion,position.staff_version_id)
    if version.annulled_at:raise ValueError('Версію штатки анульовано.')
    if start<version.valid_from or version.valid_to and (end is None or end>version.valid_to):raise ValueError('Призначення виходить за період версії штату.')
    if position.annulled_at:raise ValueError('Посаду анульовано; вона не є джерелом фактичного призначення.')
    if position.valid_from and start<position.valid_from or position.valid_to and (end is None or end>position.valid_to):raise ValueError('Призначення виходить за період чинності посади.')
    if position.org_unit_id is None:return  # Explicit transitional legacy, never guessed.
    unit=org_checked(db,position.org_unit_id)
    if start<unit.formed_on or unit.dissolved_on and (end is None or end>unit.dissolved_on):raise ValueError('Призначення виходить за період існування підрозділу.')
    rows=Repo.coverages(db,[position.org_unit_id])
    if not any(c.staff_version_id==position.staff_version_id and c.valid_from<=start and (c.valid_to is None or end is not None and end<=c.valid_to) for c in rows):
        raise ValueError('Посада не має однозначного джерела чинності на весь період призначення.')


def effective_end(db,position,version,on):
    limits=[end for end in (position.valid_to,version.valid_to) if end is not None]
    if position.org_unit_id:
        limits.extend(c.valid_to for c in Repo.coverages(db,[position.org_unit_id]) if c.staff_version_id==version.id and c.valid_from<=on and (c.valid_to is None or c.valid_to>=on) and c.valid_to is not None)
    return min(limits) if limits else None


def replace_coverage(db,actor_id,version,unit_ids,start,end):
    period(start,end)
    if version.annulled_at:raise ValueError('Версію джерела анульовано.')
    if start<version.valid_from or version.valid_to and (end is None or end>version.valid_to):raise ValueError('Покриття виходить за період версії.')
    units={u.id:u for u in Repo.units(db,unit_ids)}
    if len(units)!=len(set(unit_ids)):raise ValueError('Не всі підрозділи існують.')
    for u in units.values():
        if u.annulled_at or start<u.formed_on or u.dissolved_on and (end is None or end>u.dissolved_on):raise ValueError('Покриття виходить за період існування підрозділу.')
    old=Repo.coverages(db,unit_ids)
    replaced=[c for c in old if c.staff_version_id!=version.id and (c.valid_to is None or c.valid_to>=start) and (end is None or c.valid_from<=end)]
    if any(c.valid_from>start for c in replaced):raise ValueError('Є пізніше незалежне джерело: спочатку явно узгодьте його період.')
    affected=Repo.position_ids(db,unit_ids,[c.staff_version_id for c in replaced])
    conflicts=Repo.affected_assignments(db,affected,start)
    if conflicts:raise ValueError('Спочатку явно завершіть призначення до початку нової версії: '+', '.join(str(a.id) for a in conflicts)+'. Автоматичного перенесення немає.')
    for c in replaced:
        if c.valid_from==start:c.annulled_at=datetime.now(UTC);c.annulment_reason=f'Явно заміщено версією {version.id} з {start.isoformat()}'
        else:c.valid_to=start-timedelta(days=1)
    db.flush()
    for unit_id in sorted(set(unit_ids)):
        same=[c for c in old if c.staff_version_id==version.id and c.org_unit_id==unit_id and (c.valid_to is None or c.valid_to>=start) and (end is None or c.valid_from<=end)]
        if same:
            if len(same)==1 and same[0].valid_from<=start and (same[0].valid_to is None or end is not None and end<=same[0].valid_to):continue
            raise ValueError('Покриття цієї версії вже існує з іншим періодом.')
        db.add(OrgCoverage(org_unit_id=unit_id,staff_version_id=version.id,valid_from=start,valid_to=end))
        audit(db,actor_id,unit_id,'coverage',after={'version_id':version.id,'from':start.isoformat(),'to':end.isoformat() if end else None})
    db.flush()


def bind_structure(db,actor_id,structure_id,unit_id,revision):
    with organization_write(db,actor_id,'bind'):
        unit=org_checked(db,unit_id)
        if unit.kind not in ROSTER_KINDS:raise ValueError('Структуру можна прив’язати лише до роти або вище.')
        structure=checked(db,StaffStructure,structure_id,revision)
        if structure.org_unit_id not in (None,unit_id):raise ValueError('Історичну структуру вже зіставлено; автоматичної зміни належності немає.')
        other=Repo.structure(db,unit_id)
        if other and other.id!=structure.id:raise ValueError('Цей підрозділ уже має незалежну історію штатки.')
        structure.org_unit_id=unit_id;audit(db,actor_id,unit_id,'map',after={'structure_id':structure_id})


def bind_positions(db,actor_id,version_id,mappings):
    if not mappings:raise ValueError('Виберіть посади для явного зіставлення.')
    with organization_write(db,actor_id,'bind'):
        version=checked(db,StaffVersion,version_id);structure=checked(db,StaffStructure,version.staff_structure_id)
        if version.annulled_at:raise ValueError('Анульовану версію не можна зіставляти.')
        if structure.org_unit_id is None:raise ValueError('Спочатку явно прив’яжіть структуру до підрозділу.')
        scope=snapshot(db,structure.org_unit_id,version.valid_from)
        ids=set(scope['owner_unit_ids']);prepared=[]
        for mapping in mappings:
            p=checked(db,Position,int(mapping['position_id']),int(mapping['revision']));unit_id=int(mapping['org_unit_id']);managed=int(mapping['managed_unit_id']) if mapping.get('managed_unit_id') else None
            if p.staff_version_id!=version.id or unit_id not in ids or managed is not None and managed not in ids:raise ValueError('Посада або підрозділ не належать вибраній області.')
            if p.org_unit_id not in (None,unit_id):raise ValueError('Історичну належність посади не переписують; створіть нову версію.')
            why=None
            if p.managed_unit_id not in (None,managed):
                from app.services.organization import reason
                why=reason(mapping.get('reason'))
            prepared.append((p,unit_id,managed,why))
        for unit_id in sorted({item[1] for item in prepared}):replace_coverage(db,actor_id,version,[unit_id],version.valid_from,version.valid_to)
        for p,unit_id,managed,why in prepared:
            before={'position_id':p.position_id,'org_unit_id':p.org_unit_id,'managed_unit_id':p.managed_unit_id}
            p.org_unit_id=unit_id;p.managed_unit_id=managed
            audit(db,actor_id,unit_id,'map',before=before,after={'position_id':p.position_id,'managed_unit_id':managed},reason=why)
        db.flush()


def unit_lifecycle_guard(db,unit_id,end=None):
    positions=Repo.linked_positions(db,unit_id)
    if end is None and positions:raise ValueError('Підрозділ має штатні посади. Спочатку явно опрацюйте їхні залежності.')
    if end is not None:
        for c in Repo.coverages(db,[unit_id]):
            if c.valid_to is None or c.valid_to>end:raise ValueError('Спочатку явно завершіть джерела штатки та призначення підрозділу.')


def require_complete_mapping(db,unit_id,on):
    if Repo.unbound_structure_at(db,on):
        raise ValueError('Є чинні legacy-структури без організаційного власника. Спочатку явно зіставте їх, щоб незалежна версія не дублювала невідомі джерела.')
    tree=OrganizationService.tree(db,on);nodes={u['id']:u for u in tree['units']};chain=[];key=unit_id
    while key in nodes:
        chain.append(key);key=nodes[key].get('parent_id')
    pending=Repo.unmapped_for_owners(db,chain,on)
    if pending:raise ValueError('Є незіставлені посади у вихідній структурі. Спочатку явно зіставте їх з організаційними ID.')


def page_data(db,actor_id,scope_id,on):
    authorize(db,actor_id,'view',scope_id);context=snapshot(db,scope_id,on)
    from app.validators.position_validator import POSITION_ATTRIBUTES
    from app.services.person_picker import person_options
    names={person['id']:person['label'] for person in person_options(db,on)}
    def pos(p):return {'id':p.position_id,'version_id':p.staff_version_id,'number':p.position_number,'unit_id':p.org_unit_id,'managed_unit_id':p.managed_unit_id,'revision':p.revision,'values':{key:getattr(p,key) for key in POSITION_ATTRIBUTES}}
    return {'selected':context['selected'],'owner':context['owner'],'on':on.isoformat(),'units':context['nodes'],
        'structures':[{'id':s.id,'name':s.name,'org_unit_id':s.org_unit_id,'revision':s.revision} for s in Repo.all_structures(db)],
        'versions':[{'id':v.id,'name':v.name,'structure_id':v.staff_structure_id,'valid_from':v.valid_from.isoformat(),'valid_to':v.valid_to.isoformat() if v.valid_to else None,'revision':v.revision} for v in Repo.all_versions(db)],
        'positions':[pos(p) for p in context['positions']], 'legacy_positions':[pos(p) for p in Repo.unbound_positions(db)],
        'coverages':[{'id':c.id,'revision':c.revision,'unit_id':c.org_unit_id,'version_id':c.staff_version_id,'from':c.valid_from.isoformat(),'to':c.valid_to.isoformat() if c.valid_to else None} for c in Repo.coverages(db,context['unit_ids'])],
        'receipts':[{'id':r.id,'mode':r.mode,'scope':r.scope_unit_id,'version_id':r.staff_version_id,'withdrawn_at':r.withdrawn_at.isoformat() if r.withdrawn_at else None} for r in Repo.receipts(db)],
        'queue':[{'id':q.id,'person_id':a.person_id,'person_label':names.get(a.person_id,f'ID {a.person_id}'),'assignment_id':a.id,
                  'replacement_position_id':q.replacement_position_id,'original_start':a.assigned_from.isoformat(),'original_end':a.assigned_to.isoformat() if a.assigned_to else None,
                  'order_number':a.assignment_order_number,'order_date':a.assignment_order_date.isoformat() if a.assignment_order_date else None,
                  'release_number':a.release_order_number,'release_date':a.release_order_date.isoformat() if a.release_order_date else None,
                  'completion_reason':a.completion_reason,'completion_note':a.completion_note,'revision':q.revision} for q,a in Repo.queue_details(db)]}


def resolve_reassignment(db,actor_id,key,revision,position_id,start,end,details):
    from app.models import Person
    from app.models.organization_staff import OrgReassignment
    from app.services.staff_service import StaffService,official_start,order_values,completion_values
    from app.services.assignment_audit import record_change
    period(start,end);official_start(start)
    with organization_write(db,actor_id,'reassignment'):
        queue=checked(db,OrgReassignment,key,revision)
        if queue.resolved_assignment_id:raise ValueError('Цю потребу вже опрацьовано.')
        original=checked(db,PersonAssignment,queue.assignment_id)
        if original.annulled_at is None:raise ValueError('Початкове призначення не анульоване; повторне призначення не створюється.')
        target=checked(db,Position,position_id);assert_position_period(db,target,start,end)
        checked(db,Person,original.person_id)
        record=PersonAssignment(person_id=original.person_id,staff_position_id=target.position_id,assigned_from=start,assigned_to=end,
            **order_values(details.get('order_number'),details.get('order_date')),
            **completion_values(details.get('release_number'),details.get('release_date'),details.get('completion_reason'),details.get('completion_note')))
        db.add(record);db.flush();record_change(db,record,'create',actor_id=actor_id)
        queue.resolved_assignment_id=record.id
        audit(db,actor_id,target.org_unit_id,'reassignment',after={'queue_id':key,'assignment_id':record.id,'original_assignment_id':original.id})
        return record.id


def close_coverage(db,actor_id,key,revision,end):
    from app.models.staff import exact_date
    exact_date(end)
    with organization_write(db,actor_id,'coverage'):
        coverage=checked(db,OrgCoverage,key,revision)
        if coverage.annulled_at or end<coverage.valid_from or coverage.valid_to and end>coverage.valid_to:raise ValueError('Завершення джерела не подовжує та не анулює його період.')
        positions=Repo.position_ids(db,[coverage.org_unit_id],[coverage.staff_version_id])
        if any(a.assigned_to is None or a.assigned_to>end for a in Repo.affected_assignments(db,positions)):
            raise ValueError('Спочатку явно завершіть призначення в цій області не пізніше обраної дати.')
        before={'coverage_id':key,'to':coverage.valid_to.isoformat() if coverage.valid_to else None}
        coverage.valid_to=end
        audit(db,actor_id,coverage.org_unit_id,'coverage',before=before,after={'coverage_id':key,'to':end.isoformat()})

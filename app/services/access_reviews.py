"""Transactional review queue for factual personnel changes; no grant materialization."""
from sqlalchemy import event,inspect
from sqlalchemy.orm import Session
from app.models import User,PersonAssignment,Position
from app.models.organization import OrgUnitState
from app.models.access import PositionAccessPolicy,AccessRule,AccessAudit
from app.repositories.access_repository import AccessRepository as Repo

@event.listens_for(Session,'before_flush')
def collect(session,context,instances):
    people=set();positions=set()
    for row in session.new|session.dirty:
        state=inspect(row)
        if isinstance(row,User) and state.attrs.person_id.history.has_changes():
            people.update(v for v in [row.person_id,*state.attrs.person_id.history.deleted] if v)
        elif isinstance(row,PersonAssignment):
            if row not in session.new and not any(state.attrs[k].history.has_changes() for k in ('person_id','staff_position_id','assigned_from','assigned_to','annulled_at')):continue
            ids=[row.staff_position_id,*state.attrs.staff_position_id.history.deleted]
            for key in ids:
                p=session.get(Position,key) if key else None
                if p and p.managed_unit_id:people.update(v for v in [row.person_id,*state.attrs.person_id.history.deleted] if v)
        elif isinstance(row,Position) and state.attrs.managed_unit_id.history.has_changes():positions.add(row.position_id)
        elif isinstance(row,OrgUnitState) and session.info.get('access_org_action')=='reparent' and state.attrs.primary_parent_id.history.has_changes():
            positions.update(p.position_id for p in Repo.all(session,Position) if p.managed_unit_id)
        elif isinstance(row,PositionAccessPolicy):positions.add(row.position_id)
        elif isinstance(row,AccessRule) and row.policy_id:
            policy=session.get(PositionAccessPolicy,row.policy_id)
            if policy:positions.add(policy.position_id)
    if people or positions:
        pending=session.info.setdefault('access_review_pending',{'people':set(),'positions':set()})
        pending['people'].update(people);pending['positions'].update(positions)

@event.listens_for(Session,'after_flush_postexec')
def enqueue(session,context):
    pending=session.info.pop('access_review_pending',None)
    if not pending:return
    people=pending['people']|set(Repo.affected_people(session,pending['positions']))
    for user in Repo.linked_users(session,people):
        key=Repo.review(session,user.id,'Кадрове призначення, керівний зв’язок або затверджена політика змінилися. Перевірте підсумкові права.')
        if key:
            session.add(AccessAudit(actor_user_id=session.info.get('access_actor'),target_user_id=user.id,operation='review_open',reason='Автоматичний контроль кадрових змін',before={},after={'review_id':key}))

@event.listens_for(Session,'after_rollback')
def discard(session):session.info.pop('access_review_pending',None)

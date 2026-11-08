"""Security 1.4 synthetic accounts, actual MFA, isolated SQLite and deny-first sources."""
from datetime import datetime,date as D,UTC,timedelta
import pytest
from sqlalchemy import create_engine,select,func,event,text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import DBAPIError
from app.database.base import Base
from app.models import User,Person,PersonName,StaffStructure,StaffVersion,Position,PersonAssignment
from app.models.access import *
from app.services import access,access_management as acl,accounts,organization
from app.services.staff_service import StaffService
from tests.mfa_helpers import login
from tests.test_organization_import import fields

PASSWORD='synthetic-strong-password'
START='2020-01-01T00:00:00Z';END='2030-01-01T00:00:00Z'

@pytest.fixture
def acl_store(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'access.sqlite3'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine)
    with factory() as db:
        master=accounts.create_user(db,'acl-master','Master',PASSWORD,'admin');accounts.promote_master(db,master,PASSWORD,confirmed=True)
        admin=accounts.create_user(db,'acl-admin','Admin',PASSWORD,'admin',actor_id=master)
        user=accounts.create_user(db,'acl-user','User',PASSWORD,'user',actor_id=admin)
        other=accounts.create_user(db,'acl-other','Other',PASSWORD,'user',actor_id=admin)
        root=organization.OrganizationService.create(db,admin,'battalion','Батальйон',D(2020,1,1))
        company=organization.OrganizationService.create(db,admin,'company','Рота',D(2020,1,1),parent_id=root)
        child=organization.OrganizationService.create(db,admin,'platoon','Взвод',D(2020,1,1),parent_id=company)
        outside=organization.OrganizationService.create(db,admin,'company','Інша рота',D(2020,1,1),parent_id=root)
        from app.models import OrgCoverage
        structure=StaffStructure(code='base',name='Штат',org_unit_id=root);db.add(structure);db.flush()
        version=StaffVersion(staff_structure_id=structure.id,name='Поточний',valid_from=D(2020,1,1));db.add(version);db.flush()
        for unit in (root,company,child,outside):db.add(OrgCoverage(org_unit_id=unit,staff_version_id=version.id,valid_from=D(2020,1,1)))
        people=[Person(tax_number='000000000'+str(i)) for i in (1,2,3)]
        db.add_all(people);db.flush()
        for p,name in zip(people,['Командир','Підлеглий','Сторонній']):db.add(PersonName(person_id=p.person_id,surname=name,name='Тест',is_active=True))
        positions=[]
        for number,unit,managed in [(1,company,child),(2,child,None),(3,outside,outside)]:
            p=Position(staff_version_id=version.id,org_unit_id=unit,managed_unit_id=managed,**fields(number));db.add(p);positions.append(p)
        db.commit()
        for p,pos in zip(people,positions):StaffService.create_assignment(db,p.person_id,pos.position_id,D(2020,1,1),actor_id=admin)
        ids={'master':master,'admin':admin,'user':user,'other':other,'root':root,'company':company,'child':child,'outside':outside,'people':[p.person_id for p in people],'positions':[p.position_id for p in positions]}
        token,_=login(db,'acl-admin',PASSWORD)
        db.info.update(access_actor=admin,access_session_hash=accounts.digest_token(token))
        yield db,ids,factory
    engine.dispose()


def rule(db,ids,category='basic',action='read',effect='ALLOW',*,unit=None,person=None,user=None):
    target=ids['user'] if user is None else user
    data={'category':category,'action':action,'effect':effect,'scope_type':'person' if person else 'unit' if unit else 'global','person_id':person,'unit_id':unit}
    return acl.save_rule(db,ids['admin'],target,data,db.get(User,target).revision,'Синтетичне підтвердження')


def bind(db,username):
    db.info.pop('access_actor',None);db.info.pop('access_session_hash',None)
    token,_=login(db,username,PASSWORD);user,session=accounts.authenticate(db,token)
    db.info.update(access_actor=user.id,access_session_hash=session.token_hash)
    return user.id


def test_roles_master_is_not_subject_admin_and_user_default_denies(acl_store):
    db,i,_=acl_store
    assert access.Access(db,i['admin']).allowed('medical',person_id=i['people'][2])
    for role in ('master','user'):
        for category in access.CATEGORIES:assert not access.Access(db,i[role]).allowed(category,person_id=i['people'][1])
    with pytest.raises(ValueError):accounts.create_user(db,'bad-role','Bad',PASSWORD,'viewer',actor_id=i['admin'])
    with pytest.raises(PermissionError):accounts.create_user(db,'bad-admin','Bad',PASSWORD,'admin',actor_id=i['admin'])
    accounts.set_active(db,i['admin'],i['user'],db.get(User,i['user']).revision,False,confirmed=True)
    rule(db,i,unit=i['company'])
    assert acl.matrix(db,i['admin'],i['user'])['editable']
    assert not acl.explain(db,i['admin'],i['user'],'basic','read',{'unit_id':i['company']})['allowed']
    with pytest.raises(PermissionError):access.Access(db,i['user'])


def test_tree_inheritance_deny_and_edit_implies_read(acl_store):
    db,i,_=acl_store
    rule(db,i,unit=i['company'],action='edit')
    e=access.Access(db,i['user']);assert e.allowed('basic',person_id=i['people'][1]) and e.allowed('basic','edit',person_id=i['people'][1])
    assert not e.allowed('basic',person_id=i['people'][2])
    rule(db,i,effect='DENY',unit=i['child'])
    e=access.Access(db,i['user']);assert not e.allowed('basic',person_id=i['people'][1]) and not e.allowed('basic','edit',person_id=i['people'][1])
    rule(db,i,person=i['people'][1])
    assert not access.Access(db,i['user']).allowed('basic',person_id=i['people'][1])


def test_unrelated_manual_rights_and_operational_parent_do_not_change_access(acl_store):
    db,i,_=acl_store
    rule(db,i,unit=i['outside'])
    organization.OrganizationService.add_operational(db,i['admin'],i['child'],i['outside'],D(2020,1,1))
    e=access.Access(db,i['user']);assert e.allowed('basic',person_id=i['people'][2]) and not e.allowed('basic',person_id=i['people'][1])


def test_date_based_primary_reparent_changes_inheritance(acl_store):
    db,i,_=acl_store
    rule(db,i,unit=i['company'])
    unit=db.get(__import__('app.models',fromlist=['OrgUnit']).OrgUnit,i['child'])
    organization.OrganizationService.revise(db,i['admin'],unit.id,unit.revision,D(2026,11,1),parent_id=i['outside'])
    before=access.Access(db,i['user'],at=datetime(2026,10,31));after=access.Access(db,i['user'],at=datetime(2026,11,2))
    assert before.allowed('basic',person_id=i['people'][1]) and not after.allowed('basic',person_id=i['people'][1])


def test_link_unique_independent_and_audited(acl_store):
    db,i,_=acl_store;before=db.scalar(select(func.count()).select_from(PersonAssignment))
    acl.link_person(db,i['admin'],i['user'],i['people'][0],db.get(User,i['user']).revision,'Прив’язку перевірено')
    with pytest.raises(ValueError,match='вже прив’язана'):acl.link_person(db,i['admin'],i['other'],i['people'][0],db.get(User,i['other']).revision,'Перевірка дубліката')
    assert db.scalar(select(func.count()).select_from(PersonAssignment))==before
    assert db.scalar(select(AccessAudit).where(AccessAudit.operation=='person_link')).actor_user_id==i['admin']


def test_automatic_leadership_is_separate_and_review_is_deduplicated(acl_store):
    db,i,_=acl_store
    rule(db,i,unit=i['outside'])
    acl.link_person(db,i['admin'],i['user'],i['people'][0],db.get(User,i['user']).revision,'Прив’язка командира')
    policy=acl.policy(db,i['admin'],i['positions'][0],[{'category':'basic','action':'read'}],'Затверджено лише базове читання',confirmed=True)
    e=access.Access(db,i['user']);assert e.allowed('basic',person_id=i['people'][1]) and e.allowed('basic',person_id=i['people'][2])
    assert not e.allowed('medical',person_id=i['people'][1]) and not e.allowed('basic','edit',person_id=i['people'][1])
    assert {r['source'] for r in e.rules}=={'manual','position'}
    acl.policy(db,i['admin'],i['positions'][0],[{'category':'basic','action':'read'}],'Повторна звірка політики',revision=db.get(PositionAccessPolicy,policy).revision,confirmed=True)
    assert db.scalar(select(func.count()).select_from(AccessReview).where(AccessReview.status=='OPEN'))==1
    task=db.scalar(select(AccessReview));acl.resolve_review(db,i['admin'],task.id,task.revision,'Ручні й автоматичні права перевірено')
    acl.policy(db,i['admin'],i['positions'][0],[],'Політику змінено',revision=db.get(PositionAccessPolicy,policy).revision,confirmed=True)
    assert db.scalar(select(func.count()).select_from(AccessReview))==2
    assert access.Access(db,i['user']).allowed('basic',person_id=i['people'][2])


def test_template_copy_confirmation_activation_and_deny_priority(acl_store):
    db,i,_=acl_store
    key=acl.template(db,i['admin'],'Базове читання',[{'category':'basic','action':'read'}],'Початковий шаблон')
    copied=acl.template(db,i['admin'],'Копія',[],'Незалежна копія',copy_from=key)
    grant=acl.assign_template(db,i['admin'],i['user'],key,i['company'],None,None,'Призначення шаблону')
    assert access.Access(db,i['user']).allowed('basic',person_id=i['people'][1])
    with pytest.raises(ValueError,match='централізовану'):acl.template(db,i['admin'],'Змінений',[],'Зміна без підтвердження',key=key,revision=db.get(AccessTemplate,key).revision)
    acl.template(db,i['admin'],'Змінений',[{'category':'basic','action':'read','effect':'DENY'}],'Підтверджена централізована зміна',key=key,revision=db.get(AccessTemplate,key).revision,confirmed=True)
    assert not access.Access(db,i['user']).allowed('basic',person_id=i['people'][1])
    assert db.scalar(select(AccessRule).where(AccessRule.template_id==copied)).effect=='ALLOW'
    acl.change_source(db,i['admin'],'template_assignment',grant,db.get(TemplateAssignment,grant).revision,False,'Деактивація призначення')
    acl.change_source(db,i['admin'],'template_assignment',grant,db.get(TemplateAssignment,grant).revision,True,'Поновлення призначення')
    bind(db,'acl-master')
    master_grant=acl.assign_template(db,i['master'],i['master'],copied,i['company'],None,None,'Явне призначення Master')
    bind(db,'acl-admin')
    with pytest.raises(PermissionError):acl.change_source(db,i['admin'],'template_assignment',master_grant,db.get(TemplateAssignment,master_grant).revision,False,'Заборонена зміна Master')


def test_temporary_rights_are_fixed_expire_and_revoke(acl_store):
    db,i,_=acl_store
    policy=acl.policy(db,i['admin'],i['positions'][0],[{'category':'basic','action':'read'}],'Затверджено політику',confirmed=True)
    key=acl.temporary(db,i['admin'],i['user'],i['positions'][0],[{'category':'basic','action':'read'}],START,END,'Тимчасове виконання')
    acl.policy(db,i['admin'],i['positions'][0],[{'category':'basic','action':'read'},{'category':'medical','action':'edit'}],'Розширена основна політика',revision=db.get(PositionAccessPolicy,policy).revision,confirmed=True)
    e=access.Access(db,i['user']);assert e.allowed('basic',person_id=i['people'][1]) and not e.allowed('medical',person_id=i['people'][1])
    assert not access.Access(db,i['user'],at=datetime(2030,1,1)).allowed('basic',person_id=i['people'][1])
    acl.change_source(db,i['admin'],'temporary',key,db.get(TemporaryAccess,key).revision,False,'Достроково відкликано')
    assert not access.Access(db,i['user']).allowed('basic',person_id=i['people'][1])


def test_delegation_cannot_escape_scope_self_elevate_or_redelegate(acl_store):
    db,i,_=acl_store
    acl.delegation(db,i['admin'],i['user'],i['company'],[['basic','read']],START,END,'Контрольоване делегування')
    bind(db,'acl-user')
    permitted={'category':'basic','action':'read','scope_type':'unit','unit_id':i['child']}
    acl.save_rule(db,i['user'],i['other'],permitted,db.get(User,i['other']).revision,'Читання підрозділу')
    for target,data in [(i['user'],permitted),(i['other'],{**permitted,'unit_id':i['outside']}),(i['other'],{**permitted,'category':'medical'})]:
        with pytest.raises(PermissionError):acl.save_rule(db,i['user'],target,data,db.get(User,target).revision,'Заборонена зміна')
    with pytest.raises(PermissionError):acl.delegation(db,i['user'],i['other'],i['company'],[['basic','read']],START,END,'Подальше делегування')
    with pytest.raises(PermissionError):acl.explain(db,i['user'],i['other'],'basic','read',{'unit_id':i['child']})


def test_stale_matrix_and_audit_failure_roll_back_all_rules(acl_store):
    db,i,_=acl_store;revision=db.get(User,i['user']).revision
    change={'category':'basic','action':'read','scope_type':'unit','unit_id':i['company'],'effect':'ALLOW'}
    acl.save_matrix(db,i['admin'],i['user'],[change],revision,'Перший запис')
    with pytest.raises(ValueError,match='змінилася'):acl.save_matrix(db,i['admin'],i['user'],[change],revision,'Застаріле редагування')
    count=db.scalar(select(func.count()).select_from(AccessRule))
    def fail(*_):raise RuntimeError('synthetic ACL audit failure')
    event.listen(AccessAudit,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):rule(db,i,person=i['people'][2])
    finally:event.remove(AccessAudit,'before_insert',fail)
    assert db.scalar(select(func.count()).select_from(AccessRule))==count


def test_fresh_mfa_required_and_audit_is_immutable(acl_store,monkeypatch):
    from app.models import UserSession
    db,i,_=acl_store;rule(db,i);session=db.get(UserSession,db.info['access_session_hash']);original=access.now();monkeypatch.setattr(access,'now',lambda:original+timedelta(minutes=6));from app.services import mfa;monkeypatch.setattr(mfa,'now',lambda:original+timedelta(minutes=6))
    with pytest.raises(PermissionError,match='MFA_REAUTH_REQUIRED'):rule(db,i)
    db.info.pop('access_actor',None)
    with pytest.raises(DBAPIError):db.execute(text('DELETE FROM access_audit'));db.commit()
    db.rollback()


def test_transfer_switches_automatic_rights_but_keeps_independent_manual_rules(acl_store):
    db,i,_=acl_store
    rule(db,i,'documents',person=i['people'][1])
    acl.link_person(db,i['admin'],i['user'],i['people'][0],db.get(User,i['user']).revision,'Прив’язано командира')
    for pos in (i['positions'][0],i['positions'][2]):acl.policy(db,i['admin'],pos,[{'category':'basic','action':'read'}],'Затверджена базова політика',confirmed=True)
    # Free the target explicitly; then use the existing signed-snapshot service path.
    occupying=db.scalar(select(PersonAssignment).where(PersonAssignment.person_id==i['people'][2]))
    StaffService.correct_assignment(db,occupying.id,occupying.revision,i['people'][2],i['positions'][2],D(2020,1,1),D(2026,10,31),actor_id=i['admin'])
    expected=StaffService.assignment_snapshot(db,i['positions'][2],i['people'][0],D(2026,11,1))
    StaffService.assign(db,i['positions'][2],i['people'][0],D(2026,11,1),expected,True,actor_id=i['admin'])
    e=access.Access(db,i['user'])
    assert not e.allowed('basic',person_id=i['people'][1])
    assert e.allowed('documents',person_id=i['people'][1])
    assert e.allowed('basic',person_id=i['people'][0])
    assert db.scalar(select(func.count()).select_from(AccessReview).where(AccessReview.status=='OPEN'))==1


def test_former_member_minimal_basic_does_not_restore_extended_access(acl_store):
    db,i,_=acl_store
    rule(db,i,'basic',unit=i['company']);rule(db,i,'medical',unit=i['company'])
    moving=db.scalar(select(PersonAssignment).where(PersonAssignment.person_id==i['people'][1]))
    occupied=db.scalar(select(PersonAssignment).where(PersonAssignment.person_id==i['people'][2]))
    StaffService.correct_assignment(db,occupied.id,occupied.revision,i['people'][2],i['positions'][2],D(2020,1,1),D(2026,10,31),actor_id=i['admin'])
    StaffService.correct_assignment(db,moving.id,moving.revision,i['people'][1],i['positions'][1],D(2020,1,1),D(2026,10,31),actor_id=i['admin'])
    StaffService.create_assignment(db,i['people'][1],i['positions'][2],D(2026,11,1),actor_id=i['admin'])
    e=access.Access(db,i['user']);assert e.allowed('basic',person_id=i['people'][1])
    for category in ('personal','medical','history','service'):assert not e.allowed(category,person_id=i['people'][1])
    rule(db,i,effect='DENY',person=i['people'][1]);assert not access.Access(db,i['user']).allowed('basic',person_id=i['people'][1])


def test_temporary_subset_cannot_drop_a_restrictive_policy_deny(acl_store):
    db,i,_=acl_store
    acl.policy(db,i['admin'],i['positions'][0],[{'category':'basic','action':'edit'},{'category':'basic','action':'read','effect':'DENY'}],'Політика із забороною',confirmed=True)
    acl.temporary(db,i['admin'],i['user'],i['positions'][0],[{'category':'basic','action':'edit'}],START,END,'Підмножина з обов’язковою забороною')
    assert not access.Access(db,i['user']).allowed('basic',person_id=i['people'][1])
    assert not access.Access(db,i['user']).allowed('basic','edit',person_id=i['people'][1])


def test_explicit_expiry_and_revocation_are_effective_without_relogin(acl_store):
    db,i,_=acl_store
    key=acl.save_rule(db,i['admin'],i['user'],{'category':'basic','action':'read','scope_type':'unit','unit_id':i['child'],'starts_at':'2026-11-01T00:00:00Z','ends_at':'2026-11-09T00:00:00Z'},db.get(User,i['user']).revision,'Точний строк')
    assert access.Access(db,i['user'],at=datetime(2026,11,8)).allowed('basic',person_id=i['people'][1])
    assert not access.Access(db,i['user'],at=datetime(2026,11,9)).allowed('basic',person_id=i['people'][1])
    acl.revoke_rule(db,i['admin'],key,db.get(AccessRule,key).revision,'Дострокове відкликання')
    assert not access.Access(db,i['user']).allowed('basic',person_id=i['people'][1])


def test_organizational_actions_are_separate_and_service_calls_are_scoped(acl_store):
    from app.models import OrgUnit
    db,i,_=acl_store
    rule(db,i,'organization','reorder',unit=i['company'])
    rule(db,i,'organization','reparent',unit=i['company'])
    bind(db,'acl-user')
    unit=db.get(OrgUnit,i['child'])
    with pytest.raises(PermissionError):organization.OrganizationService.revise(db,i['user'],unit.id,unit.revision,D(2026,1,1),name='Заборонена назва')
    with pytest.raises(PermissionError):organization.OrganizationService.revise(db,i['user'],unit.id,unit.revision,D(2026,1,1),parent_id=i['outside'])
    organization.OrganizationService.revise(db,i['user'],unit.id,unit.revision,D(2026,1,1),parent_id=None)
    assert access.Access(db,i['user']).parents[unit.id] is None


def test_matrix_revision_is_required_and_delegated_ancestors_are_context_only(acl_store):
    db,i,_=acl_store
    with pytest.raises(ValueError,match='revision'):acl.save_matrix(db,i['admin'],i['user'],[],None,'Без версії')
    acl.delegation(db,i['admin'],i['user'],i['child'],[['basic','read']],START,END,'Делеговано лише взвод')
    bind(db,'acl-user')
    result=acl.matrix(db,i['user'],i['other'])
    root=next(r for r in result['rows'] if r['key']==f'unit:{i["root"]}')
    assert root['manageable']==[] and root['effective']=={}
    assert any(r['key']==f'unit:{i["child"]}' for r in result['rows'])
    assert not any(r['key']==f'unit:{i["outside"]}' for r in result['rows'])

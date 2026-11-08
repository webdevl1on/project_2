"""Independent dated organizational identity; synthetic DB and administrators only."""
from datetime import date as D
import pytest
from sqlalchemy import create_engine,select,func,event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from app.database.base import Base
from app.models import User
from app.models.organization import OrgUnit,OrgUnitState,OrgAudit,OperationalSubordination
from app.services import accounts
from app.services.organization import OrganizationService as Service

@pytest.fixture
def organization(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'organization.sqlite3'));Base.metadata.create_all(engine)
    factory=sessionmaker(engine)
    with factory() as db:
        actor=accounts.create_user(db,'organization-admin','Тестовий Admin','synthetic-password','admin')
        yield db,actor
    engine.dispose()

def revision(db,key):return db.get(OrgUnit,key,populate_existing=True).revision

def create(db,actor,name,*,parent=None,kind='company',formed=D(2020,1,1),end=None):
    return Service.create(db,actor,kind,name,formed,parent_id=parent,dissolved_on=end)

def node(db,key,on=D(2020,1,1)):return next(item for item in Service.tree(db,on)['units'] if item['id']==key)


def test_arbitrary_depth_and_later_parent_independent_of_kind(organization):
    db,actor=organization
    child=create(db,actor,'Перший підрозділ',kind='battalion')
    parent=create(db,actor,'Пізніше внесений батько',kind='squad')
    Service.revise(db,actor,child,revision(db,child),D(2020,6,1),parent_id=parent)
    assert node(db,child,D(2020,5,31))['parent_id'] is None
    assert node(db,child,D(2020,6,1))['parent_id']==parent
    last=child
    for number in range(24):last=create(db,actor,f'Глибина {number}',parent=last,kind='other')
    tree=Service.tree(db,D(2020,7,1));assert len(tree['units'])==26
    assert tree['roots']==[parent] and node(db,child,D(2020,7,1))['kind']=='battalion'


def test_dated_names_do_not_rewrite_old_snapshots_and_stale_revision_fails(organization):
    db,actor=organization;key=create(db,actor,'Стара назва');old=revision(db,key)
    Service.revise(db,actor,key,old,D(2020,3,1),name='Нова назва')
    assert node(db,key,D(2020,2,29))['name']=='Стара назва'
    assert node(db,key,D(2020,3,1))['name']=='Нова назва'
    with pytest.raises(ValueError,match='змінився'):Service.revise(db,actor,key,old,D(2020,4,1),name='Застаріла')
    records=list(db.scalars(select(OrgAudit).where(OrgAudit.org_unit_id==key).order_by(OrgAudit.id)))
    assert records[-1].actor_user_id==actor and records[-1].before['states'][0]['name']=='Стара назва'
    assert records[-1].after['states'][-1]['name']=='Нова назва'


def test_duplicate_siblings_normalization_and_different_parents(organization):
    db,actor=organization;p=create(db,actor,'Батько 1');q=create(db,actor,'Батько 2')
    first=create(db,actor,'1 взвод',parent=p)
    create(db,actor,'1 взвод',parent=q)
    with pytest.raises(ValueError,match='Однакові'):create(db,actor,'  1   ВЗВОД ',parent=p)
    assert db.scalar(select(func.count()).select_from(OrgUnit))==4
    with pytest.raises(ValueError,match='Однакові'):Service.revise(db,actor,first,revision(db,first),D(2020,2,1),parent_id=q)
    assert node(db,first,D(2020,3,1))['parent_id']==p


def test_cycle_check_uses_every_historical_boundary(organization):
    db,actor=organization;a=create(db,actor,'А');b=create(db,actor,'Б',parent=a)
    with pytest.raises(ValueError,match='Цикл'):Service.revise(db,actor,a,revision(db,a),D(2020,2,1),parent_id=b)
    Service.revise(db,actor,b,revision(db,b),D(2020,6,1),parent_id=None)
    Service.revise(db,actor,a,revision(db,a),D(2020,6,1),parent_id=b)
    with pytest.raises(ValueError,match='Цикл'):Service.revise(db,actor,a,revision(db,a),D(2020,5,1),parent_id=b)
    assert node(db,a,D(2020,5,1))['parent_id'] is None


def test_sorting_cannot_move_units_to_other_parent(organization):
    db,actor=organization;p=create(db,actor,'Батько');a=create(db,actor,'А',parent=p);b=create(db,actor,'Б',parent=p);other=create(db,actor,'Інший корінь')
    Service.reorder(db,actor,D(2020,1,1),p,[b,a])
    assert node(db,p)['children']==[b,a]
    with pytest.raises(ValueError,match='Сортування'):Service.reorder(db,actor,D(2020,1,1),p,[a,other])
    assert node(db,other)['parent_id'] is None and node(db,a)['parent_id']==p


def test_dissolution_and_annulment_have_different_history_and_new_identity(organization):
    db,actor=organization;old=create(db,actor,'Назва')
    Service.dissolve(db,actor,old,revision(db,old),D(2020,2,29))
    assert node(db,old,D(2020,2,29))['id']==old and not Service.tree(db,D(2020,3,1))['units']
    new=create(db,actor,'Назва',formed=D(2020,3,1));assert new!=old
    with pytest.raises(ValueError):Service.annul(db,actor,new,revision(db,new),' ')
    Service.annul(db,actor,new,revision(db,new),'Помилкове формування')
    assert db.get(OrgUnit,new).annulled_at and db.get(OrgUnit,new).annulled_by==actor
    assert not Service.tree(db,D(2020,3,1))['units']
    assert create(db,actor,'Назва',formed=D(2020,3,1))!=new


def test_parent_dissolution_refused_until_children_explicitly_reparented(organization):
    db,actor=organization;parent=create(db,actor,'Батько');child=create(db,actor,'Дитина',parent=parent)
    with pytest.raises(ValueError,match='Батьківський'):Service.dissolve(db,actor,parent,revision(db,parent),D(2020,6,30))
    assert db.get(OrgUnit,parent).dissolved_on is None
    Service.revise(db,actor,child,revision(db,child),D(2020,7,1),parent_id=None)
    Service.dissolve(db,actor,parent,revision(db,parent),D(2020,6,30))
    assert node(db,child,D(2020,7,1))['parent_id'] is None


def test_operational_parent_is_separate_and_cycles_rejected(organization):
    db,actor=organization;a=create(db,actor,'А');b=create(db,actor,'Б');c=create(db,actor,'В',parent=a)
    Service.add_operational(db,actor,c,b,D(2020,2,1))
    assert node(db,c,D(2020,2,1))['parent_id']==a and node(db,c,D(2020,2,1))['operational_parent_id']==b
    with pytest.raises(ValueError,match='Цикл'):Service.add_operational(db,actor,b,c,D(2020,3,1))
    with pytest.raises(ValueError,match='перетинаються'):Service.add_operational(db,actor,c,b,D(2020,4,1))
    with pytest.raises(ValueError,match='Оперативне'):Service.dissolve(db,actor,b,revision(db,b),D(2020,6,1))


def test_unauthorized_editor_cannot_mutate_tree_and_master_can(organization):
    db,actor=organization;editor=accounts.create_user(db,'org-editor','Editor','synthetic-password','editor',actor_id=actor)
    with pytest.raises(PermissionError):create(db,editor,'Заборонено')
    accounts.promote_master(db,actor,'synthetic-password',confirmed=True)
    assert create(db,actor,'Master може')


def test_audit_failure_rolls_back_entire_tree_change(organization):
    db,actor=organization;key=create(db,actor,'Стара')
    def refuse(*args):raise RuntimeError('synthetic audit failure')
    event.listen(OrgAudit,'before_insert',refuse)
    try:
        with pytest.raises(RuntimeError):Service.revise(db,actor,key,revision(db,key),D(2020,4,1),name='Не збережена')
    finally:event.remove(OrgAudit,'before_insert',refuse)
    assert node(db,key,D(2020,5,1))['name']=='Стара'
    assert db.scalar(select(func.count()).select_from(OrgUnitState))==1


@pytest.mark.parametrize('operation',['delete_unit','change_id','delete_state','update_audit','delete_audit','overlap_state'])
def test_sqlite_identity_history_and_audit_guards(organization,operation):
    db,actor=organization;key=create(db,actor,'Тест');unit=db.get(OrgUnit,key);state=db.scalar(select(OrgUnitState));audit=db.scalar(select(OrgAudit))
    with pytest.raises(IntegrityError):
        if operation=='delete_unit':db.delete(unit)
        elif operation=='change_id':unit.id=999
        elif operation=='delete_state':db.delete(state)
        elif operation=='update_audit':audit.reason='Підміна'
        elif operation=='delete_audit':db.delete(audit)
        else:db.add(OrgUnitState(org_unit_id=key,name='Перетин',normalized_name='перетин',valid_from=D(2020,2,1)))
        db.commit()
    db.rollback();assert db.get(OrgUnit,key)


def test_history_includes_annulled_units_and_reorder_rejects_stale_versions(organization):
    db,actor=organization;a=create(db,actor,'А');b=create(db,actor,'Б');stamps={a:revision(db,a),b:revision(db,b)}
    Service.revise(db,actor,a,revision(db,a),D(2020,2,1),name='А нове')
    with pytest.raises(ValueError,match='змінилися'):Service.reorder(db,actor,D(2020,1,1),None,[b,a],revisions=stamps)
    Service.annul(db,actor,b,revision(db,b),'Зайвий запис')
    assert Service.history(db,b)['unit']['annulment_reason']=='Зайвий запис'
    assert Service.tree(db,D(2020,1,1))['inactive_units'][0]['id']==b


def test_operational_close_preserves_history_and_allows_dissolution(organization):
    db,actor=organization;a=create(db,actor,'А');b=create(db,actor,'Б')
    edge=Service.add_operational(db,actor,a,b,D(2020,2,1));row=db.get(OperationalSubordination,edge)
    Service.close_operational(db,actor,edge,row.revision,D(2020,4,30))
    Service.dissolve(db,actor,b,revision(db,b),D(2020,4,30))
    assert node(db,a,D(2020,5,1))['operational_parent_id'] is None
    assert Service.history(db,a)['operational'][0]['valid_to']=='2020-04-30'



def test_multiple_operational_parents_remain_separate_from_primary(organization):
    db,actor=organization;a=create(db,actor,'А');b=create(db,actor,'Б');c=create(db,actor,'В')
    Service.add_operational(db,actor,a,b,D(2020,1,1));Service.add_operational(db,actor,a,c,D(2020,1,1))
    result=node(db,a);assert result['parent_id'] is None and result['operational_parent_id'] is None
    assert result['operational_parent_ids']==[b,c]

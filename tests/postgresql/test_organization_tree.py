"""PostgreSQL 17 organizational invariants and direct-writer races, project2_ci only."""
from tests.access_helpers import legacy_user
from datetime import date as D
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
from sqlalchemy import text,select,func,event
from sqlalchemy.exc import DBAPIError
from app.models.organization import OrgUnit,OrgUnitState,OrgAudit
from app.services.organization import OrganizationService as Service
from app.services import accounts

@pytest.fixture
def organizational(pg_factory):
    with pg_factory() as db:actor=legacy_user(db,'organization-admin','Тестовий Admin','synthetic-password','admin')
    return pg_factory,actor

def unit(factory,actor,name,*,parent=None):
    with factory() as db:return Service.create(db,actor,'company',name,D(2020,1,1),parent_id=parent)

def raw_unit(connection,name,parent=None):
    key=connection.scalar(text("INSERT INTO org_units(kind,formed_on,sort_order,created_at,updated_at,revision) VALUES ('company','2020-01-01',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1) RETURNING id"))
    connection.execute(text("INSERT INTO org_unit_states(org_unit_id,name,normalized_name,primary_parent_id,valid_from,created_at,updated_at,revision) VALUES (:key,:name,'deliberately-not-canonical',:parent,'2020-01-01',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"),{'key':key,'name':name,'parent':parent})
    return key


def test_raw_sql_temporal_name_uniqueness_canonicalization_and_annul_namespace(organizational):
    factory,actor=organizational;engine=factory.kw['bind'];parent=unit(factory,actor,'Батько');other=unit(factory,actor,'Інший батько')
    with engine.begin() as db:first=raw_unit(db,'  1   ВЗВОД  ',parent)
    with pytest.raises(DBAPIError),engine.begin() as db:raw_unit(db,'1 взвод',parent)
    with engine.begin() as db:raw_unit(db,'1 взвод',other)
    with factory() as db:
        assert db.scalar(select(OrgUnitState.normalized_name).where(OrgUnitState.org_unit_id==first))=='1 взвод'
        Service.annul(db,actor,first,db.get(OrgUnit,first).revision,'Помилковий запис')
    with engine.begin() as db:assert raw_unit(db,'1 взвод',parent)!=first


def test_raw_sql_historical_cycle_only_when_periods_intersect(organizational):
    factory,actor=organizational;engine=factory.kw['bind'];a=unit(factory,actor,'А');b=unit(factory,actor,'Б',parent=a)
    with factory() as db:
        Service.revise(db,actor,b,db.get(OrgUnit,b).revision,D(2020,6,1),parent_id=None)
        Service.revise(db,actor,a,db.get(OrgUnit,a).revision,D(2020,6,1),parent_id=b)
    with pytest.raises(DBAPIError),engine.begin() as db:
        db.execute(text("UPDATE org_unit_states SET primary_parent_id=:b WHERE org_unit_id=:a AND valid_from='2020-01-01'"),{'a':a,'b':b})
    with factory() as db:assert Service.tree(db,D(2020,7,1))['roots']==[b]


def test_raw_sql_multiple_operational_parents_and_temporal_cycles(organizational):
    factory,actor=organizational;engine=factory.kw['bind'];a=unit(factory,actor,'А');b=unit(factory,actor,'Б');c=unit(factory,actor,'В')
    sql="INSERT INTO org_operational_subordinations(org_unit_id,parent_id,valid_from,valid_to,created_at,updated_at,revision) VALUES (:child,:parent,:start,:end,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"
    with engine.begin() as db:
        db.execute(text(sql),{'child':a,'parent':b,'start':D(2020,1,1),'end':D(2020,5,31)})
        db.execute(text(sql),{'child':a,'parent':c,'start':D(2020,1,1),'end':None})
        db.execute(text(sql),{'child':b,'parent':a,'start':D(2020,6,1),'end':None})
    with pytest.raises(DBAPIError),engine.begin() as db:db.execute(text(sql),{'child':b,'parent':a,'start':D(2020,5,1),'end':D(2020,5,31)})
    with factory() as db:assert len(Service.history(db,a)['operational'])==2


@pytest.mark.parametrize('operation',['dissolve','annul','delete','identity','audit_update','audit_delete','missing_state'])
def test_raw_sql_lifetimes_identity_and_append_only_audit(organizational,operation):
    factory,actor=organizational;engine=factory.kw['bind'];parent=unit(factory,actor,'Батько');child=unit(factory,actor,'Дитина',parent=parent)
    sql={'dissolve':"UPDATE org_units SET dissolved_on='2020-05-31' WHERE id=:key",'annul':"UPDATE org_units SET annulled_at=CURRENT_TIMESTAMP,annulment_reason='Помилка' WHERE id=:key",'delete':'DELETE FROM org_units WHERE id=:key','identity':'UPDATE org_units SET id=999 WHERE id=:key','audit_update':"UPDATE org_audit SET reason='Підміна'",'audit_delete':'DELETE FROM org_audit','missing_state':"UPDATE org_unit_states SET valid_to='2020-01-31' WHERE org_unit_id=:key"}[operation]
    with pytest.raises(DBAPIError),engine.begin() as db:db.execute(text(sql),{'key':parent})
    with factory() as db:assert db.get(OrgUnit,parent).annulled_at is None and db.get(OrgUnit,parent).dissolved_on is None


def test_concurrent_raw_sibling_creates_only_one_can_commit(organizational):
    factory,actor=organizational;engine=factory.kw['bind'];parent=unit(factory,actor,'Батько');barrier=Barrier(2)
    def create(index):
        try:
            with engine.begin() as db:
                barrier.wait(timeout=5);raw_unit(db,'Одна назва',parent)
            return True
        except DBAPIError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(create,[1,2]))==[False,True]
    with factory() as db:assert db.scalar(select(func.count()).select_from(OrgUnit))==2


def test_concurrent_primary_reparents_do_not_create_cycle(organizational):
    factory,actor=organizational;engine=factory.kw['bind'];a=unit(factory,actor,'А');b=unit(factory,actor,'Б');barrier=Barrier(2)
    def change(pair):
        try:
            with engine.begin() as db:
                barrier.wait(timeout=5);db.execute(text('UPDATE org_unit_states SET primary_parent_id=:parent WHERE org_unit_id=:child'),{'child':pair[0],'parent':pair[1]})
            return True
        except DBAPIError:return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(change,[(a,b),(b,a)]))==[False,True]


def test_postgresql_org_audit_failure_rolls_back_history(organizational):
    factory,actor=organizational;key=unit(factory,actor,'Стара назва')
    with factory() as db:
        def fail(*args):raise RuntimeError('synthetic audit failure')
        event.listen(OrgAudit,'before_insert',fail)
        try:
            with pytest.raises(RuntimeError):Service.revise(db,actor,key,db.get(OrgUnit,key).revision,D(2020,3,1),name='Нова назва')
        finally:event.remove(OrgAudit,'before_insert',fail)
        assert Service.tree(db,D(2020,4,1))['units'][0]['name']=='Стара назва'
        assert db.scalar(select(func.count()).select_from(OrgUnitState))==1


def test_same_root_name_allowed_only_for_nonoverlapping_lifetimes_and_state_periods(organizational):
    factory,actor=organizational;engine=factory.kw['bind']
    with factory() as db:
        first=Service.create(db,actor,'company','Те саме ім’я',D(2020,1,1),dissolved_on=D(2020,2,29))
        second=Service.create(db,actor,'company','Те саме ім’я',D(2020,3,1))
        assert second!=first
    with pytest.raises(DBAPIError),engine.begin() as db:
        db.execute(text("INSERT INTO org_unit_states(org_unit_id,name,normalized_name,valid_from,valid_to,created_at,updated_at,revision) VALUES (:key,'Перетин','перетин','2020-01-15','2020-02-01',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1)"),{'key':first})
    with pytest.raises(DBAPIError),engine.begin() as db:
        db.execute(text("UPDATE org_units SET formed_on='2020-02-29' WHERE id=:key"),{'key':second})
        db.execute(text("UPDATE org_unit_states SET valid_from='2020-02-29' WHERE org_unit_id=:key"),{'key':second})


def test_raw_sql_annulment_of_empty_unit_requires_a_reason(organizational):
    factory,actor=organizational;key=unit(factory,actor,'Порожній підрозділ');engine=factory.kw['bind']
    with pytest.raises(DBAPIError),engine.begin() as db:
        db.execute(text('UPDATE org_units SET annulled_at=CURRENT_TIMESTAMP WHERE id=:key'),{'key':key})
    with factory() as db:assert db.get(OrgUnit,key).annulled_at is None

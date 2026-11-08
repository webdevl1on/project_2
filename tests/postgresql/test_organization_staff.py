"""Roster source invariants and additive migration on isolated PostgreSQL 17 schemas."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date as D
from pathlib import Path
from threading import Barrier
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event,func,select,text
from sqlalchemy.exc import DBAPIError
from app.models import StaffStructure,StaffVersion,Position,Person,PersonAssignment,AssignmentAudit
from app.models.organization import OrgAudit
from app.models.organization_staff import OrgCoverage,OrgStaffImport,OrgReassignment
from app.database.postgresql import require_postgresql_schema
from app.services import accounts,organization,organization_import as importing,organization_staff as staff
from app.services.staff_service import StaffService,assignments_at
from tests.test_organization_import import fields,excel

ON=D(2026,1,1)

@pytest.fixture
def roster(pg_factory):
    with pg_factory() as db:
        actor=accounts.create_user(db,'roster-admin','Синтетичний Admin','synthetic-password','admin')
        root=organization.OrganizationService.create(db,actor,'battalion','Батальйон',D(2020,1,1))
        company=organization.OrganizationService.create(db,actor,'company','1 рота',D(2020,1,1),parent_id=root)
        child=organization.OrganizationService.create(db,actor,'platoon','1 взвод',D(2020,1,1),parent_id=company)
        other=organization.OrganizationService.create(db,actor,'company','2 рота',D(2020,1,1),parent_id=root)
        structure=StaffStructure(code='base',name='Базова структура',org_unit_id=root);db.add(structure);db.flush()
        version=StaffVersion(staff_structure_id=structure.id,name='Базовий штат',valid_from=D(2020,1,1));db.add(version);db.flush()
        for unit in (root,company,child,other):db.add(OrgCoverage(org_unit_id=unit,staff_version_id=version.id,valid_from=D(2020,1,1)))
        positions=[]
        for number,unit in [(1,company),(2,child),(3,other)]:
            row=Position(staff_version_id=version.id,org_unit_id=unit,**fields(number));db.add(row);positions.append(row)
        person=Person();db.add(person);db.commit()
        ids={'actor':actor,'root':root,'company':company,'child':child,'other':other,'structure':structure.id,'version':version.id,'positions':[p.position_id for p in positions],'person':person.person_id}
    return pg_factory,ids


def test_independent_company_snapshot_is_vacant_and_does_not_change_battalion(roster):
    factory,ids=roster
    with factory() as db:
        original=db.get(StaffVersion,ids['version']);revision=original.revision
        prepared=importing.preview(db,ids['actor'],excel([(['1 взвод'],2,'Оператор')]),ids['child'],'official',ON,name='Ротна')
        key=importing.confirm(db,ids['actor'],prepared,[3]);version=db.get(OrgStaffImport,key).staff_version_id
        before=staff.snapshot(db,ids['root'],D(2025,12,31))['positions'];after=staff.snapshot(db,ids['root'],ON)['positions']
        assert {p.position_id for p in before}==set(ids['positions'])
        assert {p.position_number for p in after}=={1,2,3} and len(after)==3
        assert [p.staff_version_id for p in after if p.org_unit_id!=ids['other']]==[version,version]
        assert next(p for p in after if p.org_unit_id==ids['other']).position_id==ids['positions'][2]
        assert db.get(StaffVersion,original.id).revision==revision and db.get(StaffVersion,original.id).valid_to is None
        assert db.scalar(select(func.count()).select_from(PersonAssignment))==0
    require_postgresql_schema(factory.kw['bind'])


def test_official_requires_explicit_completion_and_keeps_original_orders(roster):
    factory,ids=roster
    with factory() as db:
        aid=StaffService.create_assignment(db,ids['person'],ids['positions'][1],D(2024,1,2),order_number='21',actor_id=ids['actor'])
        prepared=importing.preview(db,ids['actor'],excel([(['1 взвод'],2,'Оператор')]),ids['child'],'official',ON,name='Ротна')
        with pytest.raises(ValueError,match='явно завершіть'):importing.confirm(db,ids['actor'],prepared,[3])
        assert db.scalar(select(func.count()).select_from(StaffVersion))==1
        StaffService.correct_assignment(db,aid,db.get(PersonAssignment,aid).revision,ids['person'],ids['positions'][1],D(2024,1,2),D(2025,12,31),actor_id=ids['actor'])
        importing.confirm(db,ids['actor'],prepared,[3])
        assert assignments_at(db,D(2025,12,31)).one().id==aid
        assert assignments_at(db,ON).count()==0
        assert db.get(PersonAssignment,aid).assignment_order_number=='21'


def test_replacement_reuses_active_number_preserves_audit_and_reassigns_actual_dates(roster):
    factory,ids=roster
    with factory() as db:
        aid=StaffService.create_assignment(db,ids['person'],ids['positions'][1],D(2024,1,2),order_number='21',order_date=D(2024,1,1),actor_id=ids['actor'])
        prepared=importing.preview(db,ids['actor'],excel([(['1 взвод'],2,'Виправлена посада')]),ids['child'],'replace',ON)
        key=importing.confirm(db,ids['actor'],prepared,[3],replace_ids=[ids['positions'][1]],confirm_removal=True,reason='Помилково завантажена штатка')
        old=db.get(PersonAssignment,aid);queue=db.scalar(select(OrgReassignment));qid,revision,target=queue.id,queue.revision,queue.replacement_position_id
        assert old.annulled_at and db.get(Position,old.staff_position_id).annulled_at
        assert db.get(Position,target).position_number==2 and target!=old.staff_position_id
        new=staff.resolve_reassignment(db,ids['actor'],qid,revision,target,D(2024,1,2),None,{'order_number':'21','order_date':D(2024,1,1)})
        assert db.get(PersonAssignment,new).assigned_from==D(2024,1,2)
        assert db.get(PersonAssignment,new).assignment_order_number=='21'
        assert [r.operation for r in db.scalars(select(AssignmentAudit).order_by(AssignmentAudit.id))]==['create','annul','create']
        with pytest.raises(ValueError,match='подальші призначення'):importing.withdrawal(db,ids['actor'],key,'Відкликання')


@pytest.mark.parametrize('sql',[
    "UPDATE org_staff_coverage SET valid_to='2025-12-31' WHERE org_unit_id=:unit",
    "UPDATE positions SET valid_to='2025-12-31' WHERE position_id=:position",
    "UPDATE positions SET org_unit_id=:other WHERE position_id=:position",
    "UPDATE staff_versions SET annulled_at=CURRENT_TIMESTAMP,annulment_reason='Помилка' WHERE id=:version",
    "UPDATE org_units SET kind='platoon' WHERE id=:root",
])
def test_direct_sql_cannot_invalidate_sources_or_historical_links(roster,sql):
    factory,ids=roster;engine=factory.kw['bind']
    with factory() as db:aid=StaffService.create_assignment(db,ids['person'],ids['positions'][1],D(2024,1,2),actor_id=ids['actor'])
    with pytest.raises(DBAPIError),engine.begin() as db:db.execute(text(sql),{'unit':ids['child'],'position':ids['positions'][1],'other':ids['other'],'version':ids['version'],'root':ids['root']})
    with factory() as db:assert db.get(PersonAssignment,aid).annulled_at is None and db.get(Position,ids['positions'][1]).org_unit_id==ids['child']


def test_concurrent_confirmation_is_idempotent_across_sessions(roster):
    factory,ids=roster
    with factory() as db:prepared=importing.preview(db,ids['actor'],excel([(['1 взвод'],2,'Оператор')]),ids['child'],'official',ON,name='Ротна')
    barrier=Barrier(2)
    def confirm(_):
        with factory() as db:
            barrier.wait(timeout=5);return importing.confirm(db,ids['actor'],prepared,[3])
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(confirm,[1,2]))
    assert results[0]==results[1]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(OrgStaffImport))==1
        assert db.scalar(select(func.count()).select_from(StaffVersion))==2
        assert len(staff.snapshot(db,ids['root'],ON)['positions'])==3


def test_source_cutover_racing_assignment_cannot_commit_invalid_state(roster):
    factory,ids=roster;engine=factory.kw['bind'];barrier=Barrier(2)
    def write(kind):
        try:
            barrier.wait(timeout=5)
            if kind=='source':
                with engine.begin() as db:db.execute(text("UPDATE org_staff_coverage SET valid_to='2025-12-31' WHERE org_unit_id=:unit"),{'unit':ids['child']})
            else:
                with factory() as db:StaffService.create_assignment(db,ids['person'],ids['positions'][1],ON,actor_id=ids['actor'])
            return True
        except (ValueError,DBAPIError):return False
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(write,['source','assignment']))==[False,True]
    with factory() as db:
        coverage=db.scalar(select(OrgCoverage).where(OrgCoverage.org_unit_id==ids['child']))
        assignment=db.scalar(select(PersonAssignment))
        assert (coverage.valid_to==D(2025,12,31) and assignment is None) or (coverage.valid_to is None and assignment is not None)


def test_org_audit_failure_rolls_back_replacement_and_assignment_audit(roster):
    factory,ids=roster
    with factory() as db:
        aid=StaffService.create_assignment(db,ids['person'],ids['positions'][1],D(2024,1,2),actor_id=ids['actor'])
        prepared=importing.preview(db,ids['actor'],excel([(['1 взвод'],2,'Оператор')]),ids['child'],'replace',ON)
        def fail(*_):raise RuntimeError('synthetic organization audit failure')
        event.listen(OrgAudit,'before_insert',fail)
        try:
            with pytest.raises(RuntimeError):importing.confirm(db,ids['actor'],prepared,[3],replace_ids=[ids['positions'][1]],confirm_removal=True,reason='Помилка')
        finally:event.remove(OrgAudit,'before_insert',fail)
        assert db.get(PersonAssignment,aid).annulled_at is None and db.get(Position,ids['positions'][1]).annulled_at is None
        assert db.scalar(select(func.count()).select_from(OrgStaffImport))==0
        assert db.scalar(select(func.count()).select_from(AssignmentAudit))==1


@pytest.mark.parametrize('pg_factory',['0007_mfa_sessions'],indirect=True)
def test_additive_0008_preserves_legacy_records_without_guessing_mapping_or_audit(pg_factory):
    engine=pg_factory.kw['bind']
    with pg_factory() as db:
        actor=accounts.create_user(db,'legacy-admin','Попередній Admin','synthetic-password','admin')
        structure=db.scalar(text("INSERT INTO staff_structures(code,name,created_at,updated_at,revision) VALUES ('legacy','Архівний штат',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1) RETURNING id"))
        version=db.scalar(text("INSERT INTO staff_versions(staff_structure_id,name,valid_from,created_at,updated_at,revision) VALUES (:structure,'Попередня версія','2020-01-01',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1) RETURNING id"),{'structure':structure})
        from app.validators.position_validator import POSITION_ATTRIBUTES
        columns=','.join(POSITION_ATTRIBUTES);binds=','.join(':'+name for name in POSITION_ATTRIBUTES)
        position=db.scalar(text(f'INSERT INTO positions(staff_version_id,{columns},created_at,updated_at,revision) VALUES (:version,{binds},CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1) RETURNING position_id'),{**fields(1),'version':version})
        person=db.scalar(text('INSERT INTO persons DEFAULT VALUES RETURNING person_id'))
        assignment=db.scalar(text("INSERT INTO person_assignments(person_id,staff_position_id,assigned_from,assignment_order_number,assignment_order_date,created_at,updated_at,revision) VALUES (:person,:position,'2021-01-02','21','2021-01-01',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP,1) RETURNING id"),{'person':person,'position':position});db.commit()
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with engine.begin() as db:
        cfg.attributes['connection']=db;command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    require_postgresql_schema(engine)
    with pg_factory() as db:
        assert db.get(StaffStructure,structure).org_unit_id is None
        p=db.get(Position,position);assert p.org_unit_id is None and p.annulled_at is None
        a=db.get(PersonAssignment,assignment);assert a.assigned_from==D(2021,1,2) and a.assignment_order_number=='21'
        assert db.scalar(select(func.count()).select_from(OrgAudit))==0
        assert db.scalar(select(func.count()).select_from(OrgCoverage))==0

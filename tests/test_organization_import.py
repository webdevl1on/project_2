"""Scoped import decisions on isolated synthetic organizations and staffing."""
from datetime import date as D
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine,select,func,event
from sqlalchemy.orm import sessionmaker
from app.database.base import Base
from app.models import StaffStructure,StaffVersion,Position,Person,PersonAssignment
from app.models.organization import OrgUnit,OrgAudit
from app.models.organization_staff import OrgCoverage,OrgStaffImport,OrgStaffImportRow,OrgReassignment
from app.services import accounts,organization,organization_staff,organization_import as service
from app.services.staff_service import StaffService
from app.validators.position_validator import POSITION_ATTRIBUTES,validate_position

ON=D(2026,1,1)


def fields(number,name='Стрілець'):
    return validate_position(dict(zip(POSITION_ATTRIBUTES,[number,'CODE','1 рота',name,*[name]*7])))


def excel(rows,depth=1):
    book=Workbook();ws=book.active;ws.title='positions'
    ws.append(['parent',*[f'child_{i}' for i in range(1,depth+1)],*POSITION_ATTRIBUTES]);ws.append(['пояснення'])
    for path,number,name in rows:
        ws.append([*path,*[None]*(depth+1-len(path)),*fields(number,name).values()])
    stream=BytesIO();book.save(stream);book.close();return stream.getvalue()


@pytest.fixture
def store(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'org-import.sqlite3'),connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(engine)
    with factory() as db:
        actor=accounts.create_user(db,'import-admin','Admin','synthetic-password','admin')
        root=organization.OrganizationService.create(db,actor,'battalion','Батальйон',D(2020,1,1))
        company=organization.OrganizationService.create(db,actor,'company','1 рота',D(2020,1,1),parent_id=root)
        platoon=organization.OrganizationService.create(db,actor,'platoon','1 взвод',D(2020,1,1),parent_id=company)
        other=organization.OrganizationService.create(db,actor,'platoon','2 взвод',D(2020,1,1),parent_id=company)
        outside=organization.OrganizationService.create(db,actor,'company','2 рота',D(2020,1,1),parent_id=root)
        structure=StaffStructure(org_unit_id=root,code='base',name='Базовий штат');db.add(structure);db.flush()
        version=StaffVersion(staff_structure_id=structure.id,name='Базова версія',valid_from=D(2020,1,1));db.add(version);db.flush()
        for unit in [root,company,platoon,other,outside]:db.add(OrgCoverage(org_unit_id=unit,staff_version_id=version.id,valid_from=D(2020,1,1)))
        db.flush();positions=[]
        for number,unit in [(1,company),(2,platoon),(3,other),(4,outside)]:
            p=Position(staff_version_id=version.id,org_unit_id=unit,**fields(number));db.add(p);positions.append(p)
        db.commit()
        yield db,actor,{'root':root,'company':company,'platoon':platoon,'other':other,'outside':outside,'version':version.id,'positions':[p.position_id for p in positions]},factory
    engine.dispose()


def test_add_partial_confirmation_keeps_conflicts_and_is_idempotent(store):
    db,actor,ids,_=store
    prepared=service.preview(db,actor,excel([(['1 рота','1 взвод'],5,'Оператор'),(['1 рота'],1,'Інша назва')]),ids['company'],'add',ON)
    assert prepared['rows'][0]['status']=='pending' and prepared['rows'][1]['status']=='conflict'
    key=service.confirm(db,actor,prepared,[3]);assert service.confirm(db,actor,prepared,[3])==key
    rows=list(db.scalars(select(OrgStaffImportRow).where(OrgStaffImportRow.import_id==key).order_by(OrgStaffImportRow.row_number)))
    assert [row.status for row in rows]==['accepted','conflict']
    assert db.scalar(select(func.count()).select_from(Position))==5
    with pytest.raises(ValueError,match='конфлікти'):service.confirm(db,actor,prepared,[4])
    assert db.scalar(select(func.count()).select_from(Position))==5


def test_add_new_path_other_kind_and_same_names_in_other_roots(store):
    db,actor,ids,_=store
    same=organization.OrganizationService.create(db,actor,'platoon','Нова група',D(2020,1,1),parent_id=ids['outside'])
    prepared=service.preview(db,actor,excel([(['1 рота','Нова група'],5,'Оператор')]),ids['company'],'add',ON)
    key=service.confirm(db,actor,prepared,[3]);row=db.scalar(select(OrgStaffImportRow).where(OrgStaffImportRow.import_id==key))
    position=db.get(Position,row.position_id);unit=db.get(OrgUnit,position.org_unit_id)
    assert unit.id!=same and unit.kind=='other'
    assert organization_staff.snapshot(db,ids['company'],ON)['positions'][-1].position_id==position.position_id


def test_tree_or_position_change_after_preview_is_refused(store):
    db,actor,ids,_=store
    prepared=service.preview(db,actor,excel([(['1 рота','1 взвод'],5,'Оператор')]),ids['company'],'add',ON)
    organization.OrganizationService.revise(db,actor,ids['platoon'],db.get(OrgUnit,ids['platoon']).revision,ON,name='Інша назва')
    with pytest.raises(ValueError,match='дерево змінилося'):service.confirm(db,actor,prepared,[3])
    assert db.scalar(select(func.count()).select_from(OrgStaffImport))==0


def test_official_platoon_change_clones_company_without_changing_battalion(store):
    db,actor,ids,_=store;version=db.get(StaffVersion,ids['version']);revision=version.revision
    prepared=service.preview(db,actor,excel([(['1 взвод'],2,'Оператор')]),ids['platoon'],'official',ON,name='Нова ротна')
    key=service.confirm(db,actor,prepared,[3]);receipt=db.get(OrgStaffImport,key)
    assert receipt.owner_unit_id==ids['company'] and receipt.staff_version_id!=version.id
    assert db.get(StaffVersion,version.id).revision==revision and version.valid_to is None
    actual=organization_staff.snapshot(db,ids['company'],ON)['positions']
    assert {p.position_number for p in actual}=={1,2,3}
    assert len({p.position_id for p in actual})==3 and all(p.staff_version_id==receipt.staff_version_id for p in actual)
    assert all(p.position_id not in ids['positions'] for p in actual)
    assert next(p for p in actual if p.position_number==2).name_short=='оператор'
    assert organization_staff.snapshot(db,ids['outside'],ON)['positions'][0].position_id==ids['positions'][3]
    assert db.scalar(select(func.count()).select_from(PersonAssignment))==0


def test_official_refuses_unfinished_assignments_and_rolls_back(store):
    db,actor,ids,_=store;person=Person();db.add(person);db.commit()
    assignment=StaffService.create_assignment(db,person.person_id,ids['positions'][1],D(2025,1,1),actor_id=actor)
    prepared=service.preview(db,actor,excel([(['1 взвод'],2,'Оператор')]),ids['platoon'],'official',ON,name='Нова ротна')
    with pytest.raises(ValueError,match='Спочатку явно завершіть'):service.confirm(db,actor,prepared,[3])
    assert db.scalar(select(func.count()).select_from(StaffVersion))==1
    assert db.scalar(select(func.count()).select_from(OrgStaffImport))==0
    assert db.get(PersonAssignment,assignment).assigned_to is None


def test_correct_preserves_assignment_id_and_withdraw_compensates_fields(store):
    db,actor,ids,_=store;person=Person();db.add(person);db.commit()
    aid=StaffService.create_assignment(db,person.person_id,ids['positions'][1],D(2025,1,1),actor_id=actor)
    prepared=service.preview(db,actor,excel([(['1 взвод'],2,'Оператор')]),ids['platoon'],'correct',ON)
    with pytest.raises(ValueError):service.confirm(db,actor,prepared,[3],reason='Виправлення',confirm_removal=False)
    key=service.confirm(db,actor,prepared,[3],reason='Виправлення помилкової назви',confirm_removal=True)
    assert db.get(Position,ids['positions'][1]).name_short=='оператор'
    assert db.get(PersonAssignment,aid).annulled_at is None
    service.withdrawal(db,actor,key,'Відкликано виправлення')
    assert db.get(Position,ids['positions'][1]).name_short=='стрілець'
    assert db.get(PersonAssignment,aid).annulled_at is None


def test_replace_annuls_only_selected_assignments_and_queues_real_dates(store):
    db,actor,ids,_=store;people=[Person(),Person()];db.add_all(people);db.commit()
    old=StaffService.create_assignment(db,people[0].person_id,ids['positions'][1],D(2025,1,1),order_number='125',actor_id=actor)
    untouched=StaffService.create_assignment(db,people[1].person_id,ids['positions'][2],D(2025,1,1),actor_id=actor)
    prepared=service.preview(db,actor,excel([(['1 взвод'],2,'Оператор')]),ids['platoon'],'replace',ON)
    key=service.confirm(db,actor,prepared,[3],reason='Помилкова штатка',replace_ids=[ids['positions'][1]],confirm_removal=True)
    assert db.get(PersonAssignment,old).annulled_at and db.get(PersonAssignment,untouched).annulled_at is None
    queued=db.scalar(select(OrgReassignment).where(OrgReassignment.import_id==key));assert queued.assignment_id==old and queued.replacement_position_id
    replacement=db.get(Position,queued.replacement_position_id)
    assert replacement.position_id!=ids['positions'][1] and replacement.valid_from is None
    assert db.scalar(select(func.count()).select_from(PersonAssignment))==2
    reassigned=StaffService.create_assignment(db,people[0].person_id,replacement.position_id,D(2025,1,1),order_number='125',actor_id=actor)
    assert db.get(PersonAssignment,reassigned).assigned_from==D(2025,1,1)


def test_withdrawal_refuses_later_assignments_and_never_deletes(store):
    db,actor,ids,_=store
    prepared=service.preview(db,actor,excel([(['1 рота','1 взвод'],5,'Оператор')]),ids['company'],'add',ON)
    key=service.confirm(db,actor,prepared,[3]);row=db.scalar(select(OrgStaffImportRow).where(OrgStaffImportRow.import_id==key))
    person=Person();db.add(person);db.commit();StaffService.create_assignment(db,person.person_id,row.position_id,ON,actor_id=actor)
    with pytest.raises(ValueError,match='подальші призначення'):service.withdrawal(db,actor,key,'Помилка')
    assert db.get(OrgStaffImport,key).withdrawn_at is None
    assert db.get(Position,row.position_id).annulled_at is None


def test_withdraw_created_records_annuls_without_automatic_parent_fallback(store):
    db,actor,ids,_=store
    prepared=service.preview(db,actor,excel([(['1 взвод'],2,'Оператор')]),ids['platoon'],'official',ON,name='Нова ротна')
    key=service.confirm(db,actor,prepared,[3]);receipt=db.get(OrgStaffImport,key);created=receipt.effects['created_position_ids']
    service.withdrawal(db,actor,key,'Відкликання помилкового імпорту')
    assert all(db.get(Position,key).annulled_at for key in created)
    assert not organization_staff.snapshot(db,ids['company'],ON)['positions']
    assert db.scalar(select(func.count()).select_from(Position))==7
    with pytest.raises(ValueError,match='відкликано'):service.confirm(db,actor,prepared,[3])


def test_audit_failure_rolls_back_new_version_and_all_import_objects(store):
    db,actor,ids,_=store
    prepared=service.preview(db,actor,excel([(['1 взвод'],2,'Оператор')]),ids['platoon'],'official',ON,name='Нова ротна')
    def fail(*args):raise RuntimeError('synthetic audit failure')
    event.listen(OrgAudit,'before_insert',fail)
    try:
        with pytest.raises(RuntimeError):service.confirm(db,actor,prepared,[3])
    finally:event.remove(OrgAudit,'before_insert',fail)
    assert db.scalar(select(func.count()).select_from(StaffVersion))==1
    assert db.scalar(select(func.count()).select_from(OrgStaffImport))==0
    assert db.scalar(select(func.count()).select_from(Position))==4


def test_only_conflicts_can_be_saved_for_later_without_changing_positions(store):
    db,actor,ids,_=store
    prepared=service.preview(db,actor,excel([(['1 рота'],1,'Виправлена назва')]),ids['company'],'add',ON)
    key=service.confirm(db,actor,prepared,[])
    row=db.scalar(select(OrgStaffImportRow).where(OrgStaffImportRow.import_id==key))
    assert row.status=='conflict' and db.get(Position,ids['positions'][0]).name_short=='стрілець'
    assert db.get(OrgStaffImport,key).staff_version_id==ids['version']
    service.resolve_conflict(db,actor,key,3,'correct','Звірено з офіційним примірником',row.revision)
    assert db.get(Position,ids['positions'][0]).name_short=='виправлена назва'


def test_partial_official_confirmation_keeps_historical_membership_immutable(store):
    db,actor,ids,_=store
    prepared=service.preview(db,actor,excel([(['1 рота'],1,'Командир'),(['1 рота','2 взвод'],2,'Оператор')]),ids['company'],'official',ON,name='Частково підтверджена ротна')
    key=service.confirm(db,actor,prepared,[3])
    copied=next(p for p in organization_staff.snapshot(db,ids['company'],ON)['positions'] if p.position_number==2)
    assert copied.org_unit_id==ids['platoon']
    service.confirm(db,actor,prepared,[4])
    changed=next(p for p in organization_staff.snapshot(db,ids['company'],ON)['positions'] if p.position_number==2)
    assert changed.position_id!=copied.position_id and changed.org_unit_id==ids['other']
    assert db.get(Position,copied.position_id).annulled_at and db.get(Position,copied.position_id).org_unit_id==ids['platoon']
    assert db.get(Position,ids['positions'][1]).org_unit_id==ids['platoon']
    assert service.confirm(db,actor,prepared,[4])==key
    service.withdrawal(db,actor,key,'Відкликання цієї версії')
    assert db.get(StaffVersion,db.get(OrgStaffImport,key).staff_version_id).annulled_at


def test_partial_confirmation_refuses_changed_created_positions_and_units(store):
    db,actor,ids,_=store
    prepared=service.preview(db,actor,excel([(['1 рота','Нова група'],5,'Оператор'),(['1 рота','Нова група'],6,'Водій')]),ids['company'],'add',ON)
    key=service.confirm(db,actor,prepared,[3]);row=db.scalar(select(OrgStaffImportRow).where(OrgStaffImportRow.import_id==key,OrgStaffImportRow.row_number==3))
    position=db.get(Position,row.position_id)
    organization.OrganizationService.revise(db,actor,position.org_unit_id,db.get(OrgUnit,position.org_unit_id).revision,ON,name='Інша група')
    with pytest.raises(ValueError,match='Створені підрозділи'):service.confirm(db,actor,prepared,[4])
    assert db.scalar(select(func.count()).select_from(Position))==5


def test_explicit_coverage_close_and_dissolution_keep_other_company_source(store):
    db,actor,ids,_=store;person=Person();db.add(person);db.commit()
    aid=StaffService.create_assignment(db,person.person_id,ids['positions'][1],D(2025,1,1),actor_id=actor)
    coverage=db.scalar(select(OrgCoverage).where(OrgCoverage.org_unit_id==ids['platoon']))
    with pytest.raises(ValueError,match='Спочатку явно завершіть'):organization_staff.close_coverage(db,actor,coverage.id,coverage.revision,D(2025,12,31))
    StaffService.correct_assignment(db,aid,db.get(PersonAssignment,aid).revision,person.person_id,ids['positions'][1],D(2025,1,1),D(2025,12,31),actor_id=actor)
    organization_staff.close_coverage(db,actor,coverage.id,db.get(OrgCoverage,coverage.id).revision,D(2025,12,31))
    organization.OrganizationService.dissolve(db,actor,ids['platoon'],db.get(OrgUnit,ids['platoon']).revision,D(2025,12,31))
    assert db.get(StaffVersion,ids['version']).valid_to is None
    assert organization_staff.snapshot(db,ids['outside'],ON)['positions'][0].position_id==ids['positions'][3]


def test_managed_link_correction_is_explicit_and_audited_without_moving_position(store):
    db,actor,ids,_=store;p=db.get(Position,ids['positions'][0])
    mapping=lambda target:{'position_id':p.position_id,'revision':db.get(Position,p.position_id).revision,'org_unit_id':ids['company'],'managed_unit_id':target}
    organization_staff.bind_positions(db,actor,ids['version'],[mapping(ids['platoon'])])
    with pytest.raises(ValueError,match='причину'):organization_staff.bind_positions(db,actor,ids['version'],[mapping(ids['other'])])
    organization_staff.bind_positions(db,actor,ids['version'],[{**mapping(ids['other']),'reason':'Помилково вибраний керований взвод'}])
    assert db.get(Position,p.position_id).managed_unit_id==ids['other'] and db.get(Position,p.position_id).org_unit_id==ids['company']
    assert db.scalar(select(OrgAudit).where(OrgAudit.operation=='map').order_by(OrgAudit.id.desc())).reason=='Помилково вибраний керований взвод'


def test_concurrent_repeated_confirmation_has_one_receipt_and_position(store):
    db,actor,ids,factory=store
    prepared=service.preview(db,actor,excel([(['1 рота'],5,'Оператор')]),ids['company'],'add',ON);db.rollback()
    def confirm_once(_):
        with factory() as session:return service.confirm(session,actor,prepared,[3])
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(confirm_once,[1,2]))
    assert results[0]==results[1]
    assert db.scalar(select(func.count()).select_from(OrgStaffImport))==1
    assert db.scalar(select(func.count()).select_from(Position))==5


def test_sqlite_direct_source_truncation_cannot_invalidate_an_assignment(store):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    db,actor,ids,_=store;person=Person();db.add(person);db.commit()
    aid=StaffService.create_assignment(db,person.person_id,ids['positions'][1],D(2025,1,1),actor_id=actor)
    with pytest.raises(DBAPIError):
        db.execute(text("UPDATE org_staff_coverage SET valid_to='2025-12-31' WHERE org_unit_id=:unit"),{'unit':ids['platoon']});db.commit()
    db.rollback();assert db.get(PersonAssignment,aid).assigned_to is None


def test_replace_revalidates_previewed_people_and_revisions(store):
    db,actor,ids,_=store
    prepared=service.preview(db,actor,excel([(['1 взвод'],2,'Оператор')]),ids['platoon'],'replace',ON)
    person=Person();db.add(person);db.commit()
    aid=StaffService.create_assignment(db,person.person_id,ids['positions'][1],D(2025,1,1),actor_id=actor)
    with pytest.raises(ValueError,match='Залежні призначення змінилися'):
        service.confirm(db,actor,prepared,[3],replace_ids=[ids['positions'][1]],confirm_removal=True,reason='Помилка')
    assert db.get(PersonAssignment,aid).annulled_at is None
    assert db.scalar(select(func.count()).select_from(OrgStaffImport))==0


def test_withdrawal_detects_later_import_using_created_position_as_source(store):
    db,actor,ids,_=store
    added=service.preview(db,actor,excel([(['1 рота'],5,'Радист')]),ids['company'],'add',D(2025,1,1))
    key=service.confirm(db,actor,added,[3])
    later=service.preview(db,actor,excel([(['1 взвод'],2,'Оператор')]),ids['platoon'],'official',ON,name='Ротна після доповнення')
    service.confirm(db,actor,later,[3])
    with pytest.raises(ValueError,match='залежать інші квитанції'):service.withdrawal(db,actor,key,'Помилкове доповнення')
    assert db.get(OrgStaffImport,key).withdrawn_at is None


def test_unknown_legacy_owner_requires_explicit_mapping_before_independent_import(store):
    db,actor,ids,_=store
    legacy=StaffStructure(code='unmapped',name='Не зіставлена стара структура');db.add(legacy);db.flush()
    version=StaffVersion(staff_structure_id=legacy.id,name='Стара версія',valid_from=D(2020,1,1));db.add(version);db.flush()
    db.add(Position(staff_version_id=version.id,**fields(1)));db.commit()
    with pytest.raises(ValueError,match='без організаційного власника'):
        service.preview(db,actor,excel([(['1 взвод'],2,'Оператор')]),ids['platoon'],'official',ON,name='Неоднозначна заміна')


def test_legacy_import_cannot_reintroduce_unbound_sources_after_mapping(store):
    from app.services.staff_import import preview_import,insert_prepared
    db,actor,ids,_=store
    with pytest.raises(ValueError,match='Нові посади без організаційного ID'):
        preview_import(db,excel([(['1 рота'],7,'Водій')]),None,'Не прив’язана версія',ON,None,True)
    with pytest.raises(ValueError,match='Нові посади без організаційного ID'):
        insert_prepared(db,{},'synthetic-key')


def test_invalid_excel_values_are_persisted_as_unresolved_rows_not_imported(store):
    from openpyxl import load_workbook
    db,actor,ids,_=store
    book=load_workbook(BytesIO(excel([(['1 рота'],5,'Радист')])));book['positions'].cell(3,3,D(2020,1,1))
    stream=BytesIO();book.save(stream);book.close()
    prepared=service.preview(db,actor,stream.getvalue(),ids['company'],'add',ON)
    assert prepared['rows'][0]['status']=='conflict' and not prepared['rows'][0]['position_valid']
    key=service.confirm(db,actor,prepared,[])
    saved=db.scalar(select(OrgStaffImportRow).where(OrgStaffImportRow.import_id==key));assert saved.row_number==3 and saved.status=='conflict'
    assert db.scalar(select(func.count()).select_from(Position))==4

"""Explicit hierarchy policy, historical edits and import checks on isolated data."""
from datetime import date as D
from io import BytesIO
import pytest
from openpyxl import load_workbook
from sqlalchemy import select,func
from app.models.organization import OrgUnit,OrgAudit,KIND_LEVELS,ROSTER_KINDS
from app.models import StaffVersion
from app.services.organization import OrganizationService as Service
from app.services import organization_staff,organization_import
from tests.test_organization import organization,revision,node
from tests.test_organization_import import store,excel,ON

@pytest.mark.parametrize('parent_kind,child_kind',[('platoon','regiment'),('company','company'),('crew','squad'),('battery','detachment')])
def test_reverse_and_equal_levels_are_rejected(organization,parent_kind,child_kind):
    db,actor=organization;p=Service.create(db,actor,parent_kind,'Батько',D(2020,1,1))
    with pytest.raises(ValueError,match='ієрархія'):Service.create(db,actor,child_kind,'Неможлива дитина',D(2020,1,1),parent_id=p)
    assert db.scalar(select(func.count()).select_from(OrgUnit))==1
    assert db.scalar(select(func.count()).select_from(OrgAudit))==1

@pytest.mark.parametrize('kind',['detachment','battery','team','crew','company','platoon'])
def test_new_kinds_standalone_and_skipped_levels(organization,kind):
    db,actor=organization;p=Service.create(db,actor,'unit','Частина',D(2020,1,1))
    key=Service.create(db,actor,kind,'Підрозділ',D(2020,1,1))
    Service.revise(db,actor,key,revision(db,key),D(2020,6,1),parent_id=p)
    assert node(db,key,D(2020,5,31))['parent_id'] is None
    assert node(db,key,D(2020,6,1))['hierarchy_level']==KIND_LEVELS[kind]
    if kind in ROSTER_KINDS:
        structure=organization_staff.ensure_structure(db,key)
        v=StaffVersion(staff_structure_id=structure.id,name='Власна',valid_from=D(2020,6,1));db.add(v);db.commit()
        assert db.get(StaffVersion,v.id).staff_structure_id==structure.id
    else:
        with pytest.raises(ValueError,match='Власна історія'):organization_staff.ensure_structure(db,key)
        db.rollback()

@pytest.mark.parametrize('level',[None,0,8,True,4.5,'5'])
def test_other_requires_an_explicit_integer_level(organization,level):
    db,actor=organization
    with pytest.raises(ValueError,match='рівень'):Service.create(db,actor,'other','Інший',D(2020,1,1),hierarchy_level=level)

def test_level_edit_validates_descendants_and_history_atomically(organization):
    db,actor=organization
    parent=Service.create(db,actor,'other','Інший батько',D(2020,1,1),hierarchy_level=3)
    child=Service.create(db,actor,'company','Рота',D(2020,1,1),parent_id=parent)
    with pytest.raises(ValueError,match='ієрархія'):Service.revise(db,actor,parent,revision(db,parent),D(2020,6,1),hierarchy_level=5)
    assert db.get(OrgUnit,parent).hierarchy_level==3
    Service.revise(db,actor,child,revision(db,child),D(2020,6,1),parent_id=None)
    # Earlier child history still prevents invalid reclassification of its parent.
    with pytest.raises(ValueError,match='ієрархія'):Service.revise(db,actor,parent,revision(db,parent),D(2020,6,1),hierarchy_level=5)
    Service.revise(db,actor,parent,revision(db,parent),D(2020,6,1),hierarchy_level=2)
    assert Service.history(db,parent)['audit'][-1]['after']['hierarchy_level']==2
    # Operational command may deliberately run in the opposite type direction.
    Service.add_operational(db,actor,parent,child,D(2020,1,1))

@pytest.mark.parametrize('kind,level',[('regiment',None),('other',None),('other',4),('crew',None)])
def test_excel_hierarchy_is_checked_before_confirmation(store,kind,level):
    db,actor,ids,_=store
    book=load_workbook(BytesIO(excel([(['1 рота','Новий'],9,'Радист')])));sheet=book['positions']
    columns={c.value:c.column for c in sheet[1]}
    sheet.cell(3,columns['child_1_kind'],kind)
    sheet.cell(3,columns['child_1_level']).value=level
    stream=BytesIO();book.save(stream);book.close()
    prepared=organization_import.preview(db,actor,stream.getvalue(),ids['company'],'add',ON)
    if kind=='crew':
        receipt=organization_import.confirm(db,actor,prepared,[3]);assert receipt
        assert db.scalar(select(OrgUnit).where(OrgUnit.kind=='crew')) is not None
    else:
        assert prepared['rows'][0]['status']=='conflict'
        with pytest.raises(ValueError,match='конфлікти'):organization_import.confirm(db,actor,prepared,[3])
        assert db.scalar(select(func.count()).select_from(OrgUnit))==5


def test_legacy_other_is_not_guessed_and_reparent_requires_known_descendants(organization):
    from app.models.organization import OrgUnitState
    db,actor=organization
    root=Service.create(db,actor,'unit','Частина',D(2020,1,1))
    company=Service.create(db,actor,'company','Рота',D(2020,1,1))
    legacy=OrgUnit(kind='other',formed_on=D(2020,1,1));db.add(legacy);db.flush()
    db.add(OrgUnitState(org_unit_id=legacy.id,name='Інший старий',normalized_name='інший старий',primary_parent_id=company,valid_from=D(2020,1,1)));db.commit()
    assert Service.history(db,legacy.id)['unit']['hierarchy_level'] is None
    with pytest.raises(ValueError,match='рівні всього дочірнього дерева'):
        Service.revise(db,actor,company,revision(db,company),D(2020,6,1),parent_id=root)
    Service.revise(db,actor,legacy.id,revision(db,legacy.id),D(2020,1,1),hierarchy_level=5)
    Service.revise(db,actor,company,revision(db,company),D(2020,6,1),parent_id=root)
    assert node(db,company,D(2020,6,1))['parent_id']==root
    assert Service.history(db,legacy.id)['audit'][-1]['before']['hierarchy_level'] is None


def test_excel_invalid_metadata_remains_json_safe_and_conflicting_paths_are_not_reclassified(store):
    import json
    db,actor,ids,_=store
    book=load_workbook(BytesIO(excel([(['1 рота','Новий'],9,'Оператор'),(['1 рота','Новий'],10,'Водій')])));ws=book['positions'];cols={c.value:c.column for c in ws[1]}
    ws.cell(3,cols['child_1_level']).value=D(2020,1,1)
    stream=BytesIO();book.save(stream)
    invalid=organization_import.preview(db,actor,stream.getvalue(),ids['company'],'add',ON)
    json.dumps(invalid);assert invalid['rows'][0]['status']=='conflict'
    ws.cell(3,cols['child_1_kind']).value='crew';ws.cell(3,cols['child_1_level']).value=None
    stream=BytesIO();book.save(stream);book.close()
    conflict=organization_import.preview(db,actor,stream.getvalue(),ids['company'],'add',ON)
    assert all(row['status']=='conflict' for row in conflict['rows'])

from tests.mfa_helpers import finish_http
"""Synthetic additional records, isolated SQLite and the existing real audit actor."""
from datetime import date
import pytest
from sqlalchemy import select, func
from app.models import Person, PersonnelAudit, PersonEducation, PersonFamilyMember, PersonDirective, GeoUnit, GeoAlias
from app.services import profile_records as service
from tests.test_name_cases import factory, client
from tests.test_documents import prepared


def test_education_minimal_optional_fields_multiple_records_and_edit(factory, prepared):
    actor, _, _, pid, _ = prepared
    with factory() as db:
        first = service.save(db, actor, pid, 'education', {'level_code':'higher_bachelor'})
        second = service.save(db, actor, pid, 'education', {'level_code':'general_secondary'})
        assert first['id'] != second['id']
        row = db.get(PersonEducation, first['id'])
        assert row.institution is None and row.started_on is None and row.ended_on is None
        updated = service.save(db, actor, pid, 'education', {'level_code':'higher_master', 'started_on':'2024-02-29', 'institution':'Тестовий заклад'}, key=row.id, revision=row.revision)
        assert updated['revision'] > first['revision']
        assert db.get(PersonEducation, row.id).started_on == date(2024,2,29)
        page = service.page(db, actor, pid, 'education')
        assert len(page['records']) == 2
        assert len(page['audit']) == 3 and all(a['actor_id'] == actor for a in page['audit'])


@pytest.mark.parametrize('fields', [{}, {'level_code':'unknown'}, {'level_code':'vocational','started_on':'_.02.2026'}, {'level_code':'vocational','ended_on':'2026-02-30'}, {'level_code':'vocational','started_on':'2026-11-01','ended_on':'2026-10-01'}])
def test_education_validation_does_not_leave_records_or_audit(factory, prepared, fields):
    actor, _, _, pid, _ = prepared
    with factory() as db:
        with pytest.raises(ValueError):service.save(db, actor, pid, 'education', fields)
        assert db.scalar(select(func.count()).select_from(PersonEducation)) == 0
        assert db.scalar(select(func.count()).select_from(PersonnelAudit)) == 0


def test_education_owner_stale_revision_and_atomic_rollback(factory, prepared, monkeypatch):
    actor, _, _, pid, _ = prepared
    with factory() as db:
        other = Person();db.add(other);db.commit();other_id=other.person_id
        saved = service.save(db, actor, pid, 'education', {'level_code':'vocational'})
        for owner, revision in [(other_id,saved['revision']),(pid,0),(pid,None)]:
            with pytest.raises(ValueError):service.save(db, actor, owner, 'education', {'level_code':'higher_master'},key=saved['id'],revision=revision)
        def fail(*args,**kwargs):raise ValueError('audit failed')
        monkeypatch.setattr(service,'audit',fail)
        with pytest.raises(ValueError,match='audit failed'):
            service.save(db, actor, pid, 'education', {'level_code':'higher_master'},key=saved['id'],revision=saved['revision'])
        assert db.get(PersonEducation,saved['id']).level_code == 'vocational'
        assert db.scalar(select(func.count()).select_from(PersonnelAudit)) == 1


def test_additional_api_uses_current_authorization_and_csrf(client, prepared):
    browser, _ = client;pid=prepared[3]
    path=f'/persons/{pid}/profile-records/education'
    assert browser.get(path).status_code in (401,403)
    logged=finish_http(browser,browser.post('/auth/login',json={'username':'admin','password':'test-password-123'})).json()
    assert browser.get(path).status_code == 200
    body={'fields':{'level_code':'vocational'}}
    assert browser.post(path,json=body).status_code == 403
    assert browser.post(path,json=body,headers={'X-CSRF-Token':logged['csrf_token']}).status_code == 200


def family_data(**changes):
    return {'kinship':'daughter', 'full_name':'Тестова Дитина', **changes}


def test_family_multiple_relatives_optional_fields_and_exact_dates(factory, prepared):
    actor, _, _, pid, _ = prepared
    with factory() as db:
        first=service.save(db,actor,pid,'family',family_data())
        second=service.save(db,actor,pid,'family',family_data(birth_on='1995-05-15', death_on='2025-01-01', phone='+380 (00) 000-00-00',address_text='  Історична адреса\nКв. 01  '))
        assert first['id'] != second['id']
        row=db.get(PersonFamilyMember,second['id'])
        assert row.address_text == '  Історична адреса\nКв. 01  '
        assert row.phone.startswith('+') and row.validation_status=='unknown'
        assert row.death_on==date(2025,1,1)
        service.save(db,actor,pid,'family',family_data(kinship='other', full_name='Уточнене ПІБ',address_text=row.address_text),key=row.id,revision=row.revision)
        assert len(service.page(db,actor,pid,'family')['records'])==2


@pytest.mark.parametrize('fields',[family_data(kinship='x'),family_data(full_name='  '),family_data(death_on='_.03.2026'),family_data(birth_on='2000-01-01',death_on='1999-01-01')])
def test_family_invalid_fields_leave_no_partial_record(factory,prepared,fields):
    actor, _, _, pid, _ = prepared
    with factory() as db:
        with pytest.raises(ValueError):service.save(db,actor,pid,'family',fields)
        assert not db.scalar(select(PersonFamilyMember))


def test_family_geography_missing_ancestors_alias_conflicts_and_stable_links(factory,prepared):
    actor, _, _, pid, _ = prepared
    with factory() as db:
        region=GeoUnit(kind='region',name='Тестова область',normalized_name='тестова область')
        other=GeoUnit(kind='region',name='Інша область',normalized_name='інша область')
        db.add_all([region,other]);db.flush()
        town=GeoUnit(kind='settlement',name='Нове місто',normalized_name='нове місто',parent_id=region.id)
        db.add(town);db.flush();db.add(GeoAlias(unit_id=town.id,name='Старе місто',normalized_name='старе місто',historical=True));db.commit()
        # Settlement first, no mandatory ancestors; historical alias remains literal.
        result=service.save(db,actor,pid,'family',family_data(settlement='Старе місто',settlement_id=town.id))
        row=db.get(PersonFamilyMember,result['id']);assert row.validation_status=='matched' and row.country_id is None
        args=family_data(settlement=row.settlement,settlement_id=row.settlement_id,region=other.name,region_id=other.id)
        conflict=service.save(db,actor,pid,'family',args,key=row.id,revision=row.revision)
        assert conflict['warnings'] and db.get(PersonFamilyMember,row.id).validation_status=='mismatch'
        assert row.settlement_id==town.id and row.settlement=='Старе місто'
        # Unknown/ambiguous text must never create a dictionary link.
        unknown=service.save(db,actor,pid,'family',family_data(settlement='Нове місто'))
        assert db.get(PersonFamilyMember,unknown['id']).settlement_id is None
        assert db.get(PersonFamilyMember,unknown['id']).validation_status=='unknown'
        town.name='Перейменоване місто';db.commit()
        assert db.get(PersonFamilyMember,row.id).settlement=='Старе місто'


def test_family_owner_and_audit_rollback(factory,prepared,monkeypatch):
    actor, _, _, pid, _ = prepared
    with factory() as db:
        result=service.save(db,actor,pid,'family',family_data())
        other=Person();db.add(other);db.commit()
        with pytest.raises(ValueError):service.save(db,actor,other.person_id,'family',family_data(),key=result['id'],revision=result['revision'])
        def fail(*args,**kwargs):raise ValueError('audit failure')
        monkeypatch.setattr(service,'audit',fail)
        with pytest.raises(ValueError):service.save(db,actor,pid,'family',family_data())
        assert db.scalar(select(func.count()).select_from(PersonFamilyMember))==1


def test_directives_minimal_multiple_exact_date_and_edit(factory,prepared):
    actor, _, _, pid, _ = prepared
    with factory() as db:
        number=service.save(db,actor,pid,'directives',{'number':'0'*300})
        dated=service.save(db,actor,pid,'directives',{'issued_on':'2026-10-31'})
        assert db.get(PersonDirective,number['id']).issued_on is None
        assert db.get(PersonDirective,dated['id']).number is None
        updated=service.save(db,actor,pid,'directives',{'number':'123/26','issued_on':'2026-10-31'},key=number['id'],revision=number['revision'])
        assert updated['revision']>number['revision']
        assert len(service.page(db,actor,pid,'directives')['records'])==2
        assert db.get(PersonDirective,number['id']).issued_on==date(2026,10,31)


@pytest.mark.parametrize('fields',[{}, {'number':'  '}, {'number':'0'*301}, {'issued_on':'_.03.2026'}, {'issued_on':'2026-02-29'}])
def test_directives_invalid_empty_partial_and_length(factory,prepared,fields):
    actor, _, _, pid, _ = prepared
    with factory() as db:
        with pytest.raises(ValueError):service.save(db,actor,pid,'directives',fields)
        assert not db.scalar(select(PersonDirective))


def test_directives_owner_revision_no_side_effects_and_rollback(factory,prepared,monkeypatch):
    from app.models import PersonAssignment, PersonnelTask, PersonServiceHistory
    actor, _, _, pid, other = prepared
    with factory() as db:
        result=service.save(db,actor,pid,'directives',{'number':'123'})
        for owner,revision in [(other,result['revision']),(pid,0)]:
            with pytest.raises(ValueError):service.save(db,actor,owner,'directives',{'number':'x'},key=result['id'],revision=revision)
        for model in (PersonAssignment,PersonnelTask,PersonServiceHistory):
            assert db.scalar(select(func.count()).select_from(model))==0
        def fail(*args,**kwargs):raise ValueError('audit failure')
        monkeypatch.setattr(service,'audit',fail)
        with pytest.raises(ValueError):service.save(db,actor,pid,'directives',{'number':'new'},key=result['id'],revision=result['revision'])
        assert db.get(PersonDirective,result['id']).number=='123'


@pytest.mark.parametrize('kind,fields',[
    ('education',{'level_code':'vocational'}),
    ('family',family_data()),
    ('directives',{'number':'VIEW-001'}),
])
def test_additional_sections_keep_existing_read_write_roles(factory,prepared,kind,fields):
    actor,editor,viewer,pid,_=prepared
    with factory() as db:
        with pytest.raises(PermissionError):service.save(db,viewer,pid,kind,fields)
        saved=service.save(db,editor,pid,kind,fields)
        assert service.page(db,viewer,pid,kind)['records'][0]['id']==saved['id']
        assert service.page(db,actor,pid,kind)['audit'][0]['actor_id']==editor

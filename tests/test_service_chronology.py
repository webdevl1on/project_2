"""Synthetic personnel only; every database is isolated."""
from datetime import date as D
import pytest
from sqlalchemy import select,func
from app.models import Person,PersonAssignment,PersonServiceHistory
from app.services.staff_service import StaffService
from tests.test_staff_history import store,setup
from tests.test_name_cases import factory,client


def test_stage1_personal_number_is_one_nullable_string(store):
    person=Person(personal_number='  000-А/7  ');store.add(person);store.commit()
    assert person.personal_number=='000-А/7'
    person.personal_number='002-Б';store.commit()
    assert store.scalar(select(func.count()).select_from(Person))==1
    assert person.personal_number=='002-Б'
    person.personal_number=' ';store.commit();assert person.personal_number is None
    with pytest.raises(ValueError):person.personal_number='x'*101


def test_stage1_assignment_orders_optional_exact_and_preserve_period(store):
    _,_,positions,people=setup(store)
    key=StaffService.create_assignment(store,people[0].person_id,positions[0].position_id,D(2026,1,1),D(2026,5,31),order_number='00125',order_date=D(2025,12,30))
    row=store.get(PersonAssignment,key)
    assert row.assignment_order_number=='00125' and row.assignment_order_date==D(2025,12,30)
    assert row.release_order_date is None
    with pytest.raises(ValueError):row.assignment_order_date='2026-03'


def test_stage1_signed_snapshot_carries_order_values(store):
    _,_,positions,people=setup(store)
    expected=StaffService.assignment_snapshot(store,positions[1].position_id,people[0].person_id,D(2026,6,1),{'number':'007','date':'2026-05-31'})
    StaffService.assign(store,positions[1].position_id,people[0].person_id,D(2026,6,1),expected,True)
    row=store.scalar(select(PersonAssignment))
    assert row.assignment_order_number=='007'


def test_stage2_orders_are_narrow_and_release_is_exclusive(store):
    _,_,positions,people=setup(store)
    key=StaffService.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    row=store.get(PersonAssignment,key);identity=(row.person_id,row.position_id,row.assigned_from)
    StaffService.correct_orders(store,key,row.revision,'126',D(2026,5,31))
    assert (row.person_id,row.position_id,row.assigned_from)==identity
    StaffService.release_assignment(store,key,row.revision,D(2026,10,15),'70',D(2026,10,10),confirmed=True)
    assert row.assigned_to==D(2026,10,14) and row.release_order_number=='70'
    assert StaffService.assignment_snapshot(store,row.position_id,None,D(2026,10,15))['target'] is None
    assert store.scalar(select(func.count()).select_from(PersonServiceHistory))==0


def test_stage2_failed_transfer_and_revision_preserve_history(store):
    _,_,positions,people=setup(store)
    first=StaffService.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    row=store.get(PersonAssignment,first);oldrevision=row.revision
    expected=StaffService.assignment_snapshot(store,positions[2].position_id,people[0].person_id,D(2026,8,1))
    StaffService.correct_orders(store,first,row.revision,'new')
    with pytest.raises(ValueError):StaffService.assign(store,positions[2].position_id,people[0].person_id,D(2026,8,1),expected,True)
    assert row.assigned_to is None
    expected=StaffService.assignment_snapshot(store,positions[2].position_id,people[0].person_id,D(2026,8,1))
    StaffService.assign(store,positions[2].position_id,people[0].person_id,D(2026,8,1),expected,True)
    assert row.assigned_to==D(2026,7,31)
    assert store.scalar(select(func.count()).select_from(PersonAssignment))==2


def test_stage3_independent_partial_history_does_not_create_staff_records(store):
    from app.services.service_chronology import save_historical,chronology
    _,_,positions,people=setup(store);pid=people[0].person_id
    StaffService.create_assignment(store,pid,positions[1].position_id,D(2026,6,1))
    key=save_historical(store,pid,{'military_unit':'Навчальна частина','position':'Історична посада','position_year':'2018','end_year':'2020','order_number':'007','is_active':'on','service_type':'contract'})
    rows=chronology(store,pid)
    assert len(rows)==2 and {r['source_type'] for r in rows}=={'assignment','historical'}
    assert store.get(PersonServiceHistory,key).position_day is None
    from app.services.person_read import full_profile
    assert full_profile(store,pid)['service_wording'] is None
    assert store.scalar(select(func.count()).select_from(PersonAssignment))==1


def test_stage4_mirage_does_not_occupy_and_can_convert(store):
    from app.services import mirage
    from app.models import PersonPositionMirage
    _,_,positions,people=setup(store);pid=people[0].person_id
    key=mirage.create(store,pid,positions[1].position_id,'Очікує наказу')
    assert store.scalar(select(func.count()).select_from(PersonAssignment))==0
    with pytest.raises(ValueError):mirage.create(store,pid,positions[2].position_id)
    record=store.get(PersonPositionMirage,key)
    expected=mirage.preview(store,key,record.revision,D(2026,6,1),{'number':'001','date':None})
    mirage.convert(store,expected,True)
    assert record.status=='converted' and record.converted_assignment_id
    assert store.scalar(select(func.count()).select_from(PersonAssignment))==1
    with pytest.raises(ValueError):mirage.convert(store,expected,True)


def test_stage4_mirage_on_occupied_position_and_cancel(store):
    from app.services import mirage
    from app.models import PersonPositionMirage
    _,_,positions,people=setup(store)
    StaffService.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    key=mirage.create(store,people[1].person_id,positions[1].position_id)
    record=store.get(PersonPositionMirage,key)
    with pytest.raises(ValueError):mirage.preview(store,key,record.revision,D(2026,8,1))
    assert record.status=='waiting' and store.scalar(select(func.count()).select_from(PersonAssignment))==1
    mirage.cancel(store,key,record.revision,'Відмова')
    assert record.status=='cancelled'


def test_stage5_unicode_contains_manual_address_and_combined_filters(store):
    from app.services.geography import save
    from app.services.service_person_positions import ServicePersonPositionFunc as Table
    _,versions,positions,people=setup(store);pid=people[0].person_id
    StaffService.create_assignment(store,pid,positions[1].position_id,D(2026,6,1))
    save(store,pid,'registration',{'country':'Україна','settlement':'Миколаївка Без Довідника'})
    data=Table.get_positions(store,version_id=versions[1].id,on=D(2026,8,1),column_filters={'full_address__contains':['МИКОЛАЇ']})
    assert len(data['rows'])==1 and 'Миколаївка' in data['rows'][0]['values']['full_address']
    assert Table.get_positions(store,version_id=versions[1].id,on=D(2026,8,1),occupancy='vacant',column_filters={'full_address__contains':['Миколаї']})['total']==0
    assert Table.get_positions(store,version_id=versions[1].id,on=D(2026,8,1),column_filters={'full_address__contains':["%' OR 1=1 --"]})['total']==0


def test_stage4_candidate_can_remain_official_elsewhere_until_explicit_conversion(store):
    from app.services import mirage
    from app.models import PersonPositionMirage
    _,_,positions,people=setup(store);pid=people[0].person_id
    old=StaffService.create_assignment(store,pid,positions[1].position_id,D(2026,6,1))
    key=mirage.create(store,pid,positions[2].position_id);record=store.get(PersonPositionMirage,key)
    assert store.get(PersonAssignment,old).assigned_to is None
    expected=mirage.preview(store,key,record.revision,D(2026,8,1))
    mirage.convert(store,expected,True)
    assert store.get(PersonAssignment,old).assigned_to==D(2026,7,31)


def old_service_database(tmp_path):
    import sqlite3
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.database.base import Base
    from app.database.service_schema import ADDED_COLUMNS
    from app.database import migrate_service_history as migration
    path=tmp_path/'prior.sqlite3';engine=create_engine(f'sqlite:///{path}');Base.metadata.create_all(engine)
    with Session(engine) as db:
        _,_,positions,people=setup(db)
        StaffService.create_assignment(db,people[0].person_id,positions[1].position_id,D(2026,6,1))
    engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE person_position_mirages')
        db.execute('DROP TRIGGER exact_assignment_orders_insert');db.execute('DROP TRIGGER exact_assignment_orders_update')
        for table,names in ADDED_COLUMNS.items():
            for name in sorted(names):db.execute(f'ALTER TABLE {table} DROP COLUMN {name}')
        before=db.execute('SELECT * FROM person_assignments').fetchall()
        triggers=db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
    return path,before,triggers


def test_migration_preserves_existing_history_and_triggers(tmp_path):
    import sqlite3
    from app.database import migrate_service_history as migration
    path,before,triggers=old_service_database(tmp_path)
    backup=migration.migrate(path)
    assert backup and backup.is_file()
    with sqlite3.connect(path) as db:
        original_columns=['id','person_id','staff_position_id','assigned_from','assigned_to','created_at','updated_at','revision']
        # Original column order comes from the previous table schema.
        with sqlite3.connect(backup) as prior:
            original_columns=[r[1] for r in prior.execute('PRAGMA table_info(person_assignments)')]
        assert db.execute('SELECT '+','.join(original_columns)+' FROM person_assignments').fetchall()==before
        assert set(triggers)<=set(db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall())
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert migration.migrate(path) is None


def test_release_can_shorten_version_bounded_assignment_without_order(store):
    _,_,positions,people=setup(store)
    key=StaffService.create_assignment(store,people[0].person_id,positions[0].position_id,D(2026,1,1),D(2026,5,31))
    row=store.get(PersonAssignment,key);rev=row.revision
    with pytest.raises(ValueError):StaffService.release_assignment(store,key,rev,D(2026,1,1),confirmed=True)
    assert row.assigned_to==D(2026,5,31) and row.revision==rev
    StaffService.release_assignment(store,key,rev,D(2026,2,1),confirmed=True)
    assert row.assigned_to==D(2026,1,31) and row.release_order_number is None


def test_mirages_multiple_candidates_and_stale_conversion_do_not_affect_officials(store):
    from app.services import mirage
    from app.models import PersonPositionMirage
    _,_,positions,people=setup(store)
    first=mirage.create(store,people[0].person_id,positions[1].position_id)
    second=mirage.create(store,people[1].person_id,positions[1].position_id)
    row=store.get(PersonPositionMirage,first)
    expected=mirage.preview(store,first,row.revision,D(2026,8,1))
    StaffService.create_assignment(store,people[2].person_id,positions[1].position_id,D(2026,6,1))
    with pytest.raises(ValueError):mirage.convert(store,expected,True)
    assert row.status=='waiting' and store.get(PersonPositionMirage,second).status=='waiting'
    assert store.scalar(select(func.count()).select_from(PersonAssignment))==1


def test_historical_edit_changes_same_record_and_rejects_stale_revision(store):
    from app.services.service_chronology import save_historical
    _,_,_,people=setup(store);pid=people[0].person_id
    key=save_historical(store,pid,{'position':'Навчальна посада','position_year':'2018','end_year':'2020'})
    record=store.get(PersonServiceHistory,key);revision=record.revision
    save_historical(store,pid,{'position':'Виправлена посада','revision':str(revision),'position_year':'2018','end_year':'2020','order_number':'55'},key)
    with pytest.raises(ValueError):save_historical(store,pid,{'position':'Інша','revision':str(revision)},key)
    assert store.scalar(select(func.count()).select_from(PersonServiceHistory))==1
    assert record.order_number=='55' and record.position_day is None
    with pytest.raises(ValueError):save_historical(store,pid,{'position':'Історична','position_year':'2020','position_month':'12','end_year':'2020','end_month':'1'})
    assert store.scalar(select(func.count()).select_from(PersonServiceHistory))==1


def test_order_dates_reject_partial_values_in_raw_sql(store):
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    _,_,positions,people=setup(store)
    key=StaffService.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    with pytest.raises(IntegrityError):store.execute(text("UPDATE person_assignments SET assignment_order_date='2026-03' WHERE id=:key"),{'key':key})
    store.rollback()
    assert store.get(PersonAssignment,key).assignment_order_date is None


def test_cross_page_http_orders_mutate_the_original_assignment(client,factory):
    browser,_=client
    with factory() as db:
        _,versions,positions,people=setup(db)
        pid=people[0].person_id;version=versions[1].id
        key=StaffService.create_assignment(db,pid,positions[1].position_id,D(2026,6,1),order_date=D(2026,5,31));revision=db.get(PersonAssignment,key).revision
    response=browser.post(f'/personnel/assignments/{key}/orders',data={'revision':revision,'assignment_order_number':'126'})
    assert response.status_code==200
    page=browser.get(f'/person_full_info/{pid}');assert '126' in page.text and 'Штатне призначення' in page.text
    with factory() as db:
        from app.services.service_person_positions import ServicePersonPositionFunc
        rows=ServicePersonPositionFunc.get_positions(db,version_id=version,on=D(2026,8,1))['rows']
        assert next(r['assignment'] for r in rows if r['assignment']).id==key
        assert next(r['assignment'] for r in rows if r['assignment']).assignment_order_number=='126'
        assert next(r['assignment'] for r in rows if r['assignment']).assignment_order_date==D(2026,5,31)
        assert db.scalar(select(func.count()).select_from(PersonServiceHistory))==0


def test_transfer_rolls_back_source_closure_when_future_target_conflicts(store):
    _,_,positions,people=setup(store)
    old=StaffService.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    StaffService.create_assignment(store,people[1].person_id,positions[2].position_id,D(2026,9,1))
    snapshot=StaffService.assignment_snapshot(store,positions[2].position_id,people[0].person_id,D(2026,8,1))
    with pytest.raises(ValueError):StaffService.assign(store,positions[2].position_id,people[0].person_id,D(2026,8,1),snapshot,True)
    row=store.get(PersonAssignment,old)
    assert row.assigned_to is None and row.completion_reason is None
    assert store.scalar(select(func.count()).select_from(PersonAssignment))==2


def test_unicode_contains_combines_exact_filter_and_empty_search(store):
    from app.services.service_person_positions import ServicePersonPositionFunc as Table
    _,versions,positions,people=setup(store)
    StaffService.create_assignment(store,people[0].person_id,positions[1].position_id,D(2026,6,1))
    rows=Table.get_positions(store,version_id=versions[1].id,on=D(2026,8,1),column_filters={'surname__contains':['ТЕСТЕН'],'unit_short':[positions[1].unit_short]})
    assert rows['total']==1
    assert Table.get_positions(store,version_id=versions[1].id,on=D(2026,8,1),column_filters={'surname__contains':['   ']})['total']==2
    from app.utils.text_search import unicode_contains
    import unicodedata
    assert unicode_contains(unicodedata.normalize('NFD','Миколаїв'),'МИКОЛАЇ')==1


def test_migration_failure_rolls_back_all_added_schema(tmp_path,monkeypatch):
    import sqlite3
    from app.database import migrate_service_history as migration
    path,before,triggers=old_service_database(tmp_path)
    def fail(adapter):raise RuntimeError('synthetic final DDL failure')
    monkeypatch.setattr(migration,'install_order_guards',fail)
    with pytest.raises(RuntimeError):migration.migrate(path)
    with sqlite3.connect(path) as db:
        assert 'personal_number' not in {r[1] for r in db.execute('PRAGMA table_info(persons)')}
        assert db.execute('SELECT * FROM person_assignments').fetchall()==before
        assert db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()==triggers
        assert db.execute("SELECT name FROM sqlite_master WHERE name='person_position_mirages'").fetchone() is None
    assert len(list(tmp_path.glob('*.before-service-history-*.sqlite3')))==1

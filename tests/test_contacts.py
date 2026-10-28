"""Synthetic contacts, tmp SQLite and explicit atomic failure checks."""
import sqlite3
from datetime import date
from sqlalchemy import select,func
from sqlalchemy.exc import IntegrityError
import pytest
from app.models import Person,PersonContact,PersonName,PersonRank,Rank
from app.services import contacts
from app.services.person_read import full_profile
from tests.test_name_cases import factory,client


def person(db):
    row=Person();db.add(row);db.commit();return row.person_id


def add(db,pid,value,kind='phone',**kw):
    contacts.mutate(db,pid,{'contact_type':kind,'value':value,**kw})
    return contacts.Repo.list(db,pid)[-1]


def test_many_contacts_fourth_phone_and_independent_primaries(factory):
    with factory() as db:
        pid=person(db)
        phones=[add(db,pid,f'+44 20 7946 00{i:02d}') for i in range(3)]
        emails=[add(db,pid,f'test{i}@example.invalid','email') for i in range(2)]
        fourth=add(db,pid,'+1 (202) 555-0104')
        for record in [phones[0],fourth,emails[0]]:
            contacts.mutate(db,pid,{'revision':str(record.revision),'action':'primary'},record.id)
        records=contacts.Repo.list(db,pid)
        assert sum(r.is_primary for r in records)==2
        assert not phones[0].is_primary and fourth.is_primary and emails[0].is_primary
        contacts.mutate(db,pid,{'revision':str(fourth.revision),'action':'unprimary'},fourth.id)
        summary=contacts.summary(contacts.page(db,pid))
        assert not summary['phone']['primary'] and summary['phone']['record'].id==phones[0].id
        assert summary['phone']['additional']==4


def test_archive_primary_and_allow_readd_preserves_history(factory):
    with factory() as db:
        pid=person(db);row=add(db,pid,'+380 (67) 123-45-67',is_primary='on')
        contacts.mutate(db,pid,{'revision':str(row.revision),'action':'archive'},row.id)
        assert not row.is_primary and not row.is_active
        second=add(db,pid,'+380671234567')
        assert second.id!=row.id and not second.is_primary
        assert len(contacts.page(db,pid)['contact_archive'])==1


def test_duplicates_normalize_but_do_not_cross_person_boundary(factory):
    with factory() as db:
        first=person(db);second=person(db)
        row=add(db,first,'+380 (67) 123-45-67')
        assert row.value=='+380 (67) 123-45-67'
        with pytest.raises(contacts.ContactError,match='уже існує'):add(db,first,'380-67-123-45-67')
        add(db,second,'380671234567')
        add(db,first,' Test+tag@EXAMPLE.invalid ','email')
        with pytest.raises(contacts.ContactError):add(db,first,'test+tag@example.INVALID','email')


@pytest.mark.parametrize('kind,value',[('phone',''),('phone','123'),('phone','+44ABC1234567'),('email','broken'),('email','a..b@example.invalid'),('email','a@-example.invalid')])
def test_invalid_values_never_create_contacts(factory,kind,value):
    with factory() as db:
        pid=person(db)
        with pytest.raises(ValueError):add(db,pid,value,kind)
        assert not contacts.Repo.list(db,pid)


def test_database_constraints_prevent_two_primary_and_active_duplicates(factory):
    with factory() as db:
        pid=person(db);add(db,pid,'+44 20 7946 0001',is_primary='on')
        db.add(PersonContact(person_id=pid,contact_type='phone',value='+44 20 7946 0002',normalized_value='442079460002',is_primary=True))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()
        db.add(PersonContact(person_id=pid,contact_type='phone',value='same',normalized_value='442079460001'))
        with pytest.raises(IntegrityError):db.commit()
        db.rollback()


def test_edit_failure_and_stale_revision_leave_old_values(factory):
    with factory() as db:
        pid=person(db);row=add(db,pid,'+44 20 7946 0001');rev=row.revision
        with pytest.raises(ValueError):contacts.mutate(db,pid,{'contact_type':'phone','value':'bad','revision':str(rev)},row.id)
        assert row.value=='+44 20 7946 0001' and row.revision==rev
        contacts.mutate(db,pid,{'contact_type':'phone','value':'+44 20 7946 0002','revision':str(rev)},row.id)
        with pytest.raises(ValueError,match='уже змінено'):contacts.mutate(db,pid,{'action':'archive','revision':str(rev)},row.id)
        assert row.is_active


def test_profile_is_unambiguous_and_does_not_invent_service(factory):
    with factory() as db:
        pid=person(db)
        db.add_all([PersonName(person_id=pid,surname='Тестенко',name='Олена',is_active=True),PersonRank(person_id=pid,rank_id=1,is_active=True)]);db.commit()
        profile=full_profile(db,pid)
        assert profile['current_name'].name=='Олена' and profile['current_rank'].rank is not None
        assert profile['service_wording'] is None and profile['profile_assignment'] is None
        db.add(PersonName(person_id=pid,surname='Інша',name='Тестова',is_active=True));db.commit()
        assert full_profile(db,pid)['current_name'] is None


def test_http_errors_and_fragment_contract(client,factory):
    browser,_=client
    with factory() as db:pid=person(db)
    error=browser.post(f'/persons/{pid}/contacts',data={'contact_type':'email','value':'broken','label':'Чернетка'})
    assert error.status_code==400 and error.json()['field']=='value'
    assert browser.post(f'/persons/{pid}/contacts',data={'contact_type':'email','value':'test@example.invalid'}).status_code==200
    assert 'test@example.invalid' in browser.get(f'/persons/{pid}/overview').text
    page=browser.get(f'/person_full_info/{pid}').text
    assert 'Фотографію не додано' in page and 'TESTING' not in page and 'data-bs-target="#contacts"' in page


def test_contact_migration_preserves_records_and_backup_and_is_idempotent(factory,tmp_path):
    from app.database import migrate_contacts as migration
    with factory() as db:pid=person(db)
    engine=factory.kw['bind'];path=engine.url.database;engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute('DROP TABLE person_contacts');before=db.execute('SELECT * FROM persons').fetchall()
    backup=migration.migrate(path)
    assert backup.is_file()
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT * FROM persons').fetchall()==before
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert migration.migrate(path) is None


def test_contact_migration_ddl_rollback(factory,monkeypatch):
    from app.database import migrate_contacts as migration
    path=factory.kw['bind'].url.database;factory.kw['bind'].dispose()
    with sqlite3.connect(path) as db:db.execute('DROP TABLE person_contacts')
    original=migration.create_table
    def fail(db,table):original(db,table);raise ValueError('synthetic failure')
    monkeypatch.setattr(migration,'create_table',fail)
    with pytest.raises(ValueError):migration.migrate(path)
    with sqlite3.connect(path) as db:assert db.execute("SELECT name FROM sqlite_master WHERE name='person_contacts'").fetchone() is None


def test_primary_switch_rolls_back_if_new_record_fails(factory,monkeypatch):
    with factory() as db:
        pid=person(db);old=add(db,pid,'+44 20 7946 0001',is_primary='on');revision=old.revision
        def fail(*args):raise RuntimeError('synthetic write failure')
        monkeypatch.setattr(contacts.Repo,'add',fail)
        with pytest.raises(RuntimeError):add(db,pid,'+44 20 7946 0002',is_primary='on')
        db.refresh(old)
        assert old.is_primary and old.revision==revision and len(contacts.Repo.list(db,pid))==1


def test_contact_cannot_be_changed_through_another_person(factory):
    with factory() as db:
        first=person(db);second=person(db);row=add(db,first,'+44 20 7946 0001')
        with pytest.raises(ValueError):contacts.mutate(db,second,{'revision':str(row.revision),'action':'archive'},row.id)
        assert row.is_active


def test_profile_reads_effective_assignments_and_explicit_service_only(factory):
    from tests.test_staff_history import setup
    from app.services.staff_service import StaffService
    from app.models import PersonServiceHistory
    with factory() as db:
        _,versions,positions,people=setup(db)
        pid=people[0].person_id
        StaffService.create_assignment(db,pid,positions[-1].position_id,date(2026,6,1),None)
        assert full_profile(db,pid)['profile_assignment'][1].position_id==positions[-1].position_id
        assert full_profile(db,pid)['service_wording'] is None
        db.add(PersonServiceHistory(person_id=pid,service_type='mobilization',is_active=True));db.commit()
        # Legacy service text must not infer an explicit document-owned basis.
        assert full_profile(db,pid)['service_wording'] is None


def test_database_failure_is_sanitized_and_rolls_back_primary(factory,monkeypatch):
    from sqlalchemy.exc import OperationalError
    with factory() as db:
        pid=person(db);old=add(db,pid,'+44 20 7946 0001',is_primary='on')
        def fail(*args):raise OperationalError('SQL',{'value':'sensitive@example.invalid'},Exception('synthetic'))
        monkeypatch.setattr(contacts.Repo,'add',fail)
        with pytest.raises(contacts.ContactError) as error:add(db,pid,'+44 20 7946 0002',is_primary='on')
        assert 'sensitive' not in str(error.value) and 'SQL' not in str(error.value)
        db.refresh(old);assert old.is_primary

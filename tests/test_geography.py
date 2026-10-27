"""Only synthetic geography and isolated SQLite."""
from datetime import date
import sqlite3
import pytest
from sqlalchemy import select
from app.models import Person, GeoUnit, GeoAlias, PersonAddress, PersonBirthplace
from app.services import geography as service
from tests.test_name_cases import factory, client


def person(db):
    obj = Person(); db.add(obj); db.commit(); return obj.person_id


def current(db, pid, kind='registration'):
    return next(r for r in service.Repo.addresses(db, pid) if r.kind == kind and r.is_active)


def directory(db):
    country = GeoUnit(kind='country', name='Україна', normalized_name='україна', iso_code='UA'); db.add(country); db.flush()
    a = GeoUnit(kind='region', name='Перша', normalized_name='перша', parent_id=country.id)
    b = GeoUnit(kind='region', name='Друга', normalized_name='друга', parent_id=country.id); db.add_all([a,b]); db.flush()
    cities = [GeoUnit(kind='settlement', name='Тестове', normalized_name='тестове', parent_id=r.id) for r in (a,b)]
    db.add_all(cities); db.flush()
    db.add(GeoAlias(unit_id=cities[0].id, name='Історичне', normalized_name='історичне', historical=True)); db.commit()
    return country, a, b, cities


def test_manual_partial_birth_and_detailed_address_preserve_text(factory):
    with factory() as db:
        pid = person(db)
        service.save(db,pid,'birthplace', {'settlement':'Історична назва', 'street':'НЕ ЗБЕРІГАТИ'})
        birth = service.Repo.birthplace(db,pid)
        assert birth.settlement == 'Історична назва' and not hasattr(birth, 'street')
        service.save(db,pid,'registration', {'house':'01А/2', 'apartment':'003Б', 'postal_code':'01234', 'country':'Україна'})
        row = current(db,pid)
        assert (row.house,row.apartment,row.postal_code) == ('01А/2','003Б','01234')
        assert row.validation_status == 'unknown' and row.date_start is None
        assert service.format_address(row) == 'Україна, буд. 01А/2, кв. 003Б, 01234'
        assert service.suggestions(db,'settlement','Тест') == []
        service.save(db,pid,'actual', {'country':'Canada','postal_code':'A1B 2C3'})
        assert current(db,pid,'actual').postal_code == 'A1B 2C3'


def test_dictionary_search_scopes_duplicates_and_historical_alias(factory):
    with factory() as db:
        country,a,b,cities=directory(db)
        assert len(service.suggestions(db,'settlement','Тес')) == 2
        scoped=service.suggestions(db,'settlement','Тес',a.id)
        assert len(scoped)==1 and scoped[0]['id']==cities[0].id and 'Перша' in scoped[0]['context']
        assert service.suggestions(db,'settlement','Істор')[0]['id']==cities[0].id
        assert service.suggestions(db,'settlement','%') == []
        for i in range(25): db.add(GeoUnit(kind='settlement',name=f'Межа {i}', normalized_name=f'межа {i}'))
        db.commit()
        assert len(service.suggestions(db,'settlement','Межа')) == 20


def test_soft_mismatch_does_not_block_and_original_snapshot_survives_rename(factory):
    with factory() as db:
        country,a,b,cities=directory(db); pid=person(db)
        warnings=service.save(db,pid,'registration',{'country':'Україна','country_id':str(country.id), 'region':'Друга','region_id':str(b.id), 'settlement':'Тестове','settlement_id':str(cities[0].id)})
        row=current(db,pid)
        assert row.validation_status=='mismatch' and any('Невідповідність' in w for w in warnings)
        assert row.region=='Друга'
        values,warnings=service.prepare(db,{'region':'Друга','region_id':str(b.id),'settlement':'Тестове'})
        assert values['settlement_id'] is None  # Never assign a guessed match.
        assert values['validation_status']=='mismatch'
        cities[0].name='Перейменоване'; db.commit()
        assert current(db,pid).settlement=='Тестове'


def test_selected_alias_matched_and_bad_reference_remains_saveable(factory):
    with factory() as db:
        _,a,_,cities=directory(db)
        values,_=service.prepare(db,{'region':'Перша','region_id':str(a.id),'settlement':'Історичне','settlement_id':str(cities[0].id)},birth=True)
        assert values['validation_status']=='matched'
        values,warnings=service.prepare(db,{'settlement':'Невідоме','settlement_id':'999999'},birth=True)
        assert values['settlement_id'] is None and values['settlement']=='Невідоме' and warnings


def test_history_is_atomic_and_stale_draft_cannot_overwrite(factory):
    with factory() as db:
        pid=person(db); service.save(db,pid,'registration',{'street':'Перша'})
        first=current(db,pid); draft={'record_id':str(first.id),'revision':str(first.revision),'street':'Друга'}
        service.save(db,pid,'registration',draft)
        db.expire_all()
        records=service.Repo.addresses(db,pid)
        assert len(records)==2 and sum(r.is_active for r in records)==1
        assert records[1].street=='Перша' and records[1].date_end is None
        with pytest.raises(ValueError,match='вже змінені'): service.save(db,pid,'registration',draft)
        row=current(db,pid)
        with pytest.raises(ValueError,match='п’ять цифр'):
            service.save(db,pid,'registration',{'record_id':str(row.id),'revision':str(row.revision),'country':'Україна','postal_code':'123'})
        assert current(db,pid).street=='Друга' and len(service.Repo.addresses(db,pid))==2


def test_ui_error_preserves_all_components_and_full_form(client,factory):
    browser,_=client
    with factory() as db: pid=person(db)
    response=browser.post(f'/persons/{pid}/geography/registration',data={'country':'Україна','postal_code':'123','house':'01А/3'})
    assert response.status_code==400 and 'value="01А/3"' in response.text and 'value="123"' in response.text
    assert '<details open>' in response.text
    assert browser.get(f'/person_full_info/{pid}').status_code==200


def test_geography_migration_backup_idempotency_and_preservation(tmp_path):
    from sqlalchemy import create_engine
    from app.database.base import Base
    from app.database import migrate_geography as migration
    path=tmp_path/'old.sqlite3'; engine=create_engine(f'sqlite:///{path}')
    Base.metadata.create_all(engine)
    engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO persons (tax_number) VALUES ('0011223344')")
        for table in reversed(migration.NEW_TABLES): db.execute(f'DROP TABLE "{table.name}"')
        before=db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()
    backup=migration.migrate(path)
    assert backup.is_file() and backup.stat().st_mode & 0o077 == 0
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT tax_number FROM persons').fetchall()==[('0011223344',)]
        assert db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name").fetchall()==before
    assert migration.migrate(path) is None


def test_address_insert_failure_rolls_back_archiving(factory,monkeypatch):
    with factory() as db:
        pid=person(db); service.save(db,pid,'registration',{'house':'Перша'})
        old=current(db,pid); revision=old.revision; key=old.id
        def fail(db, record): raise RuntimeError('synthetic failure')
        monkeypatch.setattr(service.Repo,'add',fail)
        with pytest.raises(RuntimeError):
            service.save(db,pid,'registration',{'house':'Друга','record_id':str(key),'revision':str(revision)})
        db.expire_all()
        assert len(service.Repo.addresses(db,pid))==1 and current(db,pid).id==key


def test_geography_migration_ddl_failure_rolls_back(tmp_path,monkeypatch):
    from sqlalchemy import create_engine
    from app.database.base import Base
    from app.database import migrate_geography as migration
    path=tmp_path/'rollback.sqlite3'; engine=create_engine(f'sqlite:///{path}')
    Base.metadata.create_all(engine); engine.dispose()
    with sqlite3.connect(path) as db:
        for table in reversed(migration.NEW_TABLES): db.execute(f'DROP TABLE "{table.name}"')
    original=migration.create_table
    def fail(db,table):
        original(db,table)
        raise sqlite3.OperationalError('synthetic DDL failure')
    monkeypatch.setattr(migration,'create_table',fail)
    with pytest.raises(sqlite3.OperationalError): migration.migrate(path)
    with sqlite3.connect(path) as db:
        names={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert not names & {t.name for t in migration.NEW_TABLES}
    assert len(list(tmp_path.glob('*.before-geography-*.sqlite3')))==1


def test_complete_birthplace_and_exact_optional_address_period(factory):
    with factory() as db:
        country,region,_,cities=directory(db)
        district=GeoUnit(kind='district',name='Тестовий район',normalized_name='тестовий район',parent_id=region.id)
        db.add(district); db.flush()
        community=GeoUnit(kind='community',name='Тестова громада',normalized_name='тестова громада',parent_id=district.id)
        db.add(community); db.flush(); cities[0].parent_id=community.id; db.commit()
        pid=person(db)
        data={key:unit.name for key,unit in [('country',country),('region',region),('district',district),('community',community),('settlement',cities[0])]}
        data.update({key+'_id':str(unit.id) for key,unit in [('country',country),('region',region),('district',district),('community',community),('settlement',cities[0])]})
        service.save(db,pid,'birthplace',data)
        assert service.Repo.birthplace(db,pid).validation_status=='matched'
        service.save(db,pid,'registration',{'date_start':'2025-01-01','date_end':'2025-05-31'})
        assert current(db,pid).date_end==date(2025,5,31)
        with pytest.raises(ValueError,match='повної дати'):
            service.prepare(db,{'date_start':'2025-03'})
        with pytest.raises(ValueError,match='раніше'):
            service.prepare(db,{'date_start':'2025-05-01','date_end':'2025-04-30'})

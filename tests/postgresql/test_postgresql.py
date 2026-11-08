from tests.access_helpers import legacy_user
from datetime import date as D
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from io import BytesIO
import pytest
from sqlalchemy import text,select,func,inspect
from sqlalchemy.exc import SQLAlchemyError
from app.database.base import Base
from app.database.postgresql import require_postgresql_schema
from app.models import *
from app.services import accounts,documents,document_files,medical,profile_records,geography,contacts,service_bases
from app.services.person_registration import register_person
from app.services.staff_service import StaffService
from app.models.reference_data.ranks import ReferenceRanks
from tests.test_name_cases import person_data
from tests.test_staff_history import workbook
from tests.test_database_reset import geo_package


def prepare(factory):
    with factory() as db:
        db.add(Rank(**ReferenceRanks.RANKS[0]));db.commit()
        actor=legacy_user(db,'pg-admin','Тест','test-password-123','admin')
        p=register_person(db,person_data())
        q=register_person(db,person_data(tax_number='0123456788'))
        pid,qid=p.person_id,q.person_id
    return actor,pid,qid


def test_migration_metadata_and_repetition(pg_factory):
    from alembic import command
    from alembic.config import Config
    engine=pg_factory.kw['bind'];require_postgresql_schema(engine)
    assert set(inspect(engine).get_table_names())==set(Base.metadata.tables)|{'alembic_version'}
    from pathlib import Path
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with engine.begin() as db:
        cfg.attributes['connection']=db;command.upgrade(cfg,'head');command.check(cfg)


def test_complete_personnel_and_document_crud(pg_factory,tmp_path):
    actor,pid,qid=prepare(pg_factory)
    from app.services import name_cases
    from app.services.service_person_name import ServicePersonNameFunc
    from app.services.service_person_rank import ServicePersonRankFunc
    with pg_factory() as db:
        assert db.get(Person,pid).birth_day is None
        ServicePersonNameFunc.add_new_name(pid,{'surname':'Новотестенко','name':'Тест','patronymic':'Тестович'},db)
        education=profile_records.save(db,actor,pid,'education',{'level_code':'higher_bachelor'})
        profile_records.save(db,actor,pid,'family',{'kinship':'mother','full_name':'Синтетична Родичка','address_text':'Історична адреса'})
        profile_records.save(db,actor,pid,'directives',{'number':'PG-1','issued_on':'2026-01-01'})
        geography.save(db,pid,'actual',{'settlement':'Тестове','record_id':'','revision':''})
        injury=medical.save(db,actor,pid,'injuries',{'description':'Синтетичний випадок'})['id']
        assert len(medical.page(db,actor,pid)['tasks'])==2
        exam=medical.save(db,actor,pid,'exams',{'status':'COMPLETED','basis':'INJURY','injury_id':injury,'issued_on':'2026-01-01','number':'PG-VLK','fitness':'FIT'})['id']
        assert medical.active_exam(db,pid)[0].id==exam
        medical.save(db,actor,pid,'awards',{'status':'NOT_PROCESSED','name':'Тестова відзнака'})
        medical.save(db,actor,pid,'dna',{'collected_on':'2026-01-01','envelope_number':'PG-DNA'})
        key=documents.save(db,actor,pid,'other',{'number':'PG-DOC'})
        from app.services.document_storage import DocumentStorage
        fid=document_files.attach(db,actor,pid,key,db.get(PersonDocument,key).revision,b'%PDF-1.7 test','pg.pdf','other',storage=DocumentStorage(tmp_path/'files'))
        document_files.reorder(db,actor,pid,key,[fid],db.get(PersonDocument,key).revision)
        assert profile_records.page(db,actor,pid,'education')['records'][0]['id']==education['id']
        assert documents.list_documents(db,actor,pid)[-1]['id'] is not None
        assert db.scalar(select(func.count()).select_from(PersonnelAudit))>0


@pytest.mark.parametrize('value,needle',[('ЇЖАК','їж'),('ҐРУНТ','ґрун'),('Straße','STRASSE'),('Ꭰ','ꭰ'),('İ','i\u0307'),('E\u0301','é'),('Е\u0301','Е\u0301'),('О’БРІЄН','о’бр'),(' A\u00a0 B ','a b')])
def test_unicode_equivalence(pg_factory,value,needle):
    from app.utils.text_search import unicode_contains
    with pg_factory() as db:assert db.scalar(text('SELECT unicode_contains(:v,:n)'),{'v':value,'n':needle})==unicode_contains(value,needle)


@pytest.mark.parametrize('parts,spec',[( (None,2,2024),{'mode':'range','start':'2024-02-29','end':'2024-02-29'}),((None,2,2025),{'mode':'range','start':'2024-02-29','end':'2024-02-29'}),((31,None,None),{'months':[2]}),((None,None,None),{'years':[2026],'incomplete_only':True})])
def test_date_filter_equivalence(pg_factory,parts,spec):
    from app.utils.date_query import DateFilter,possible_match
    from app.date_fields import BIRTH_DATE
    encoded=DateFilter.from_json(spec)
    with pg_factory() as db:
        actual=db.scalar(text('SELECT project2_date_match(:d,:m,:y,:spec,true,1,9999)'),{'d':parts[0],'m':parts[1],'y':parts[2],'spec':encoded.to_json()})
        assert bool(actual)==possible_match(*parts,encoded,BIRTH_DATE)


@pytest.mark.parametrize('address',[{'settlement':'смт.Прикладне','settlement_type':'смт.'},{'street':'вул.123','street_type':'вулиця'},{'region':'Київська\u00a0область','country':'Україна','settlement':'\u00a0Прикладне\u00a0'},{'country':'Україна','region':'Київська область','settlement':'Тестове','settlement_type':'село','street':'вулиця Прикладна','house':'01А/2'},{'country':'Україна','region':'Київ','settlement':'Київ'},{'country':'Інша країна','community':'Громада','street_type':'Давній шлях','street':'Прикладна','note':'Тест'}])
def test_address_formatter_equivalence(pg_factory,address):
    from app.geography import GEO_FIELDS,DETAIL_FIELDS
    from app.utils.address_format import format_address
    keys=(*GEO_FIELDS,'settlement_type',*DETAIL_FIELDS)
    with pg_factory() as db:
        actual=db.scalar(text('SELECT formatted_address('+','.join(':v'+str(i) for i in range(len(keys)))+')'),{'v'+str(i):address.get(k) for i,k in enumerate(keys)})
        assert actual==format_address(address)


def test_raw_guards_and_partial_indexes(pg_factory):
    actor,pid,qid=prepare(pg_factory)
    with pg_factory() as db:
        with pytest.raises(SQLAlchemyError):
            db.execute(text("INSERT INTO person_medical_exams(person_id,status,basis,created_at,updated_at,revision) VALUES (:p,'INTERRUPTED','OTHER',now(),now(),1)"),{'p':pid});db.commit()
        db.rollback()
        with pytest.raises(SQLAlchemyError):
            db.execute(text("UPDATE document_types SET is_primary=false WHERE code='passport'"));db.commit()
        db.rollback()
        key=documents.save(db,actor,pid,'other',{})
        with pytest.raises(SQLAlchemyError):db.execute(text('DELETE FROM document_audit'));db.commit()
        db.rollback()
        documents.archive(db,actor,pid,key,db.get(PersonDocument,key).revision)
        assert documents.save(db,actor,pid,'other',{})!=key


def parallel(factory,operations):
    barrier=Barrier(2)
    def run(operation):
        with factory() as db:
            barrier.wait()
            try:return operation(db)
            except (ValueError,SQLAlchemyError):return None
    with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(run,operations))


def test_concurrent_documents_and_copy_order(pg_factory,tmp_path):
    actor,pid,_=prepare(pg_factory)
    from app.services.document_storage import DocumentStorage
    with pg_factory() as db:
        key=documents.save(db,actor,pid,'other',{'number':'initial'});revision=db.get(PersonDocument,key).revision
    results=parallel(pg_factory,[lambda db:documents.save(db,actor,pid,'other',{'number':'one'},key=key,revision=revision),lambda db:documents.save(db,actor,pid,'other',{'number':'two'},key=key,revision=revision)])
    assert sum(r is not None for r in results)==1
    with pg_factory() as db:
        ids=[document_files.attach(db,actor,pid,key,db.get(PersonDocument,key).revision,b'%PDF-1.7 x',str(i)+'.pdf','other',storage=DocumentStorage(tmp_path/'files')) for i in range(2)]
        revision=db.get(PersonDocument,key).revision
    results=parallel(pg_factory,[lambda db:document_files.reorder(db,actor,pid,key,ids,revision) or True,lambda db:document_files.reorder(db,actor,pid,key,ids[::-1],revision) or True])
    assert sum(r is not None for r in results)==1


def test_concurrent_staff_import_assignments_and_version_revision(pg_factory):
    actor,pid,qid=prepare(pg_factory)
    from app.services.staff_import import preview_import,import_version
    with pg_factory() as db:prepared=preview_import(db,workbook(),None,'PG',D(2026,1,1),None,True)
    results=parallel(pg_factory,[lambda db:import_version(db,prepared,'same-import'),lambda db:import_version(db,prepared,'same-import')])
    assert sum(r is not None for r in results)==1
    version=next(r for r in results if r is not None)
    with pg_factory() as db:
        positions=list(db.scalars(select(Position).where(Position.staff_version_id==version)));assert positions
    results=parallel(pg_factory,[lambda db:StaffService.create_assignment(db,pid,positions[0].position_id,D(2026,1,1)),lambda db:StaffService.create_assignment(db,qid,positions[0].position_id,D(2026,1,1))])
    assert sum(r is not None for r in results)==1
    with pg_factory() as db:revision=db.get(StaffVersion,version).revision
    results=parallel(pg_factory,[lambda db:StaffService.correct_version(db,version,revision,'v-one',D(2026,1,1),None) or True,lambda db:StaffService.correct_version(db,version,revision,'v-two',D(2026,1,1),None) or True])
    assert sum(r is not None for r in results)==1


def test_concurrent_medical_selection_and_automatic_tasks(pg_factory):
    actor,pid,_=prepare(pg_factory)
    with pg_factory() as db:
        injury=medical.save(db,actor,pid,'injuries',{'description':'Тест'})
        revision=db.get(Injury,injury['id']).revision
    results=parallel(pg_factory,[lambda db:medical.save(db,actor,pid,'injuries',{'description':'one'},key=injury['id'],revision=revision),lambda db:medical.save(db,actor,pid,'injuries',{'description':'two'},key=injury['id'],revision=revision)])
    assert sum(r is not None for r in results)==1
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(PersonnelTask))==2
        ids=[medical.save(db,actor,pid,'exams',{'status':'COMPLETED','basis':'OTHER','issued_on':'2026-01-01','number':str(i),'fitness':'FIT'})['id'] for i in range(2)]
    results=parallel(pg_factory,[lambda db:medical.select_active(db,actor,pid,ids[0],None) or True,lambda db:medical.select_active(db,actor,pid,ids[1],None) or True])
    assert sum(r is not None for r in results)==1


def test_seed_dry_run_repeat_conflict_and_rollback(pg_factory):
    from app.services.seed_postgresql import seed
    with pg_factory() as db:
        report=seed(db,dry_run=True)
        assert report['new']>0 and not report['conflicts']
        assert db.scalar(select(func.count()).select_from(Rank))==0
        report=seed(db,dry_run=False);assert report['new']>0
        assert seed(db,dry_run=False)['new']==0
        rank=db.scalar(select(Rank));rank.nominative='Ручна зміна';db.commit()
        assert seed(db,dry_run=True)['conflicts']==1
        with pytest.raises(ValueError):seed(db,dry_run=False)
        assert db.get(Rank,rank.rank_id).nominative=='Ручна зміна'
        assert db.scalar(select(func.count()).select_from(Person))==0


def test_geo_hierarchy_alias_soft_validation_and_large_prefix_search(pg_factory):
    from app.services.geography import suggestions,prepare as geo_prepare
    import time
    with pg_factory() as db:
        root=GeoUnit(kind='region',name='Тестова',normalized_name='тестова');db.add(root);db.flush()
        town=GeoUnit(kind='settlement',name='Тестоград',normalized_name='тестоград',parent_id=root.id);db.add(town);db.flush()
        db.add(GeoAlias(unit_id=town.id,name='Староград',normalized_name='староград',historical=True));db.commit()
        assert suggestions(db,'settlement','Старо',root.id)[0]['id']==town.id
        values,warnings=geo_prepare(db,{'settlement':'Історична невідома','settlement_id':town.id},birth=True)
        assert values['validation_status']=='mismatch' and warnings
        db.execute(text("INSERT INTO geo_units(kind,name,normalized_name,created_at,updated_at,revision) SELECT 'settlement','Тестова одиниця '||s,'тестова одиниця '||s,now(),now(),1 FROM generate_series(1,100000) s"));db.commit()
        started=time.monotonic();assert len(suggestions(db,'settlement','Тестова одиниця 123'))==20
        elapsed=time.monotonic()-started;print('PostgreSQL 100k synthetic geographic prefix search seconds:',round(elapsed,3));assert elapsed<5


def test_concurrent_http_assignments_and_same_person_two_positions(pg_factory):
    from tests.http_auth import AuthenticatedClient as TestClient
    from app.main import app
    from app.database.db import get_db
    from tests.test_person_positions import make_position
    actor,pid,qid=prepare(pg_factory)
    with pg_factory() as db:
        sid=StaffService.create_structure(db,'http-test','Тест')
        version=StaffVersion(staff_structure_id=sid,name='HTTP',valid_from=D(2026,1,1));db.add(version);db.flush()
        p=make_position(100,'Тест','Посада','Посада');p.staff_version_id=version.id
        q=make_position(101,'Тест','Посада','Посада');q.staff_version_id=version.id
        db.add_all([p,q]);db.commit();positions=[p.position_id,q.position_id]
    # Real concurrent requests, a new PostgreSQL Session for each request.
    def session():
        with pg_factory() as db:yield db
    app.dependency_overrides[get_db]=session
    try:
        with TestClient(app) as client:
            barrier=Barrier(2)
            def request(pos):
                barrier.wait();return client.post('/staff/assignments/create',data={'person_id':pid,'position_id':pos,'assigned_from':'2026-01-01'},follow_redirects=False).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(request,positions))
            assert sorted(results)==[303,409]
    finally:app.dependency_overrides.clear()


def test_contacts_service_bases_tcc_names_ranks_events_and_staff_table(pg_factory):
    from app.services import tcc_directory,name_cases
    from tests.test_name_cases import dictionary_data
    from app.services.service_person_rank import ServicePersonRankFunc
    from app.services.seed_postgresql import seed
    from app.services.service_for_person_event import PersonEventService
    from app.services.person_read import full_profile
    from app.repositories.position_table_repository import PositionTableRepository
    from app.utils.date_query import DateFilter
    actor,pid,_=prepare(pg_factory)
    with pg_factory() as db:
        contacts.mutate(db,pid,{'contact_type':'phone','value':'+380 00 000 00 00','is_primary':'on'})
        office=tcc_directory.save(db,{'official_name':'Тестовий ТЦК','type':'district','region':'Тестова область','is_active':'on'})
        key=service_bases.save(db,pid,{'service_type':'mobilization','is_current':'on','tcc_office_id':str(office),'document_tcc_name':'Історичне формулювання'})
        assert db.get(PersonServiceBasis,key).match_status=='mismatch'
        name_cases.save_dictionary(db,dictionary_data(),verified=True)
        assert name_cases.lookup(db,'name','ТЕСТОСЛАВ','male')['found']
        db.add(Rank(**ReferenceRanks.RANKS[1]));db.commit()
        ServicePersonRankFunc.add_rank(pid,{'rank_id':2},db)
        event=EventType(event_type='PG-TEST',event_name='Тестова подія');db.add(event);db.commit()
        PersonEventService.create_person_event(pid,event.event_type_id,date_start='01.01.2026',date_end='02.01.2026',db=db)
        db.commit()
        assert db.scalar(select(func.count()).select_from(PersonEvent))==1
        from app.services.service_chronology import save_historical,chronology
        save_historical(db,pid,{'military_unit':'Тестова ВЧ','position':'Історична посада','position_month':'2','position_year':'2020'})
        assert chronology(db,pid)
        assert full_profile(db,pid)['person'].person_id==pid
        structure=StaffService.create_structure(db,'table','Тест')
        version=StaffVersion(staff_structure_id=structure,name='Тест',valid_from=D(2026,1,1));db.add(version);db.flush()
        from tests.test_person_positions import make_position
        position=make_position(900,'Тест','Посада','Посада');position.staff_version_id=version.id;db.add(position);db.commit()
        StaffService.create_assignment(db,pid,position.position_id,D(2026,1,1))
        query=PositionTableRepository(db,version.id,D(2026,1,2))
        assert query._query.count()==1
        from app.table_columns import PERSON_POSITIONS_FIELDS
        binding=PERSON_POSITIONS_FIELDS['birth_date'].date_binding
        assert binding.filter(query._query,DateFilter.from_json({'months':[3]})).count()==1
        documents.set_presence(db,actor,pid,'other','NEVER_OBTAINED')
        assert next(r for r in documents.list_documents(db,actor,pid) if r['type']=='other')['presence']=='NEVER_OBTAINED'


def test_seed_all_sources_readonly_idempotence_and_manual_preservation(pg_factory,geo_package,tmp_path):
    from app.services.seed_postgresql import seed
    from tests.test_name_cases import workbook as names_book,dictionary_data
    from tests.test_service_bases import workbook as tcc_book,office
    directory,_=geo_package
    names=tmp_path/'names.xlsx';names.write_bytes(names_book([('names_male',dictionary_data())]))
    tcc=tmp_path/'tcc.xlsx';tcc.write_bytes(tcc_book([office()]))
    staff=tmp_path/'staff.xlsx';staff.write_bytes(workbook().getvalue())
    kwargs=dict(names=names,tcc=tcc,geography=directory,staff_excel=staff,version_name='Тестова',valid_from=D(2026,1,1))
    with pg_factory() as db:
        report=seed(db,**kwargs)
        assert set(report['components'])=={'references','names','tcc','geography','staff'}
        assert report['new']>7 and report['conflicts']==0 and not report['errors']
        for model in (Rank,GeoUnit,NameDictionary,TccOffice,StaffVersion,Position):
            assert db.scalar(select(func.count()).select_from(model))==0
        report=seed(db,dry_run=False,**kwargs)
        assert report['new']>7 and not report['errors']
        assert db.scalar(select(func.count()).select_from(GeoUnit))==6
        assert db.scalar(select(func.count()).select_from(GeoCityDistrict))==1
        assert db.scalar(select(func.count()).select_from(PersonAssignment))==0
        assert db.scalar(select(func.count()).select_from(Person))==0
        report=seed(db,dry_run=False,**kwargs)
        assert report['new']==0 and report['existing']>7
        unit=db.scalar(select(GeoUnit).where(GeoUnit.kind=='settlement'));unit.name='Ручна назва';db.commit()
        with pytest.raises(ValueError):seed(db,dry_run=False,**kwargs)
        assert db.get(GeoUnit,unit.id).name=='Ручна назва'
        # Sequence remains usable after batch imports with explicit integer IDs.
        row=GeoUnit(kind='settlement',name='Окрема тестова',normalized_name='окрема тестова');db.add(row);db.commit();assert row.id>6


def test_seed_invalid_workbook_rolls_back_other_components(pg_factory,tmp_path):
    from app.services.seed_postgresql import seed
    from tests.test_name_cases import workbook as names_book,dictionary_data
    book=tmp_path/'duplicate.xlsx';book.write_bytes(names_book([('names_male',dictionary_data()),('names_male',dictionary_data())]))
    with pg_factory() as db:
        baseline={model:db.scalar(select(func.count()).select_from(model)) for model in (Rank,EventType,NameDictionary)}
        report=seed(db,names=book)
        assert report['errors']
        with pytest.raises(ValueError):seed(db,dry_run=False,names=book)
        for model in (Rank,EventType,NameDictionary):assert db.scalar(select(func.count()).select_from(model))==baseline[model]


def test_serialization_failure_is_controlled_and_rolls_back(pg_factory):
    from app.database.transactions import service_transaction
    with pg_factory() as db:
        with pytest.raises(ValueError,match='паралельних'):
            with service_transaction(db):
                db.add(Person(tax_number='0000000000'));db.flush()
                db.execute(text("DO $$ BEGIN RAISE EXCEPTION 'synthetic serialization failure' USING ERRCODE='40001'; END $$"))
        assert db.scalar(select(func.count()).select_from(Person))==0


def test_raw_sql_history_owner_and_calendar_guards(pg_factory):
    actor,pid,qid=prepare(pg_factory)
    from app.services.staff_import import preview_import,import_version
    with pg_factory() as db:
        prepared=preview_import(db,workbook(),None,'Guards',D(2026,1,1),None,True)
        version=import_version(db,prepared,'guards-import')
        position=db.scalar(select(Position).where(Position.staff_version_id==version))
        assignment=StaffService.create_assignment(db,pid,position.position_id,D(2026,1,1))
        injury=medical.save(db,actor,pid,'injuries',{'description':'Тест'})['id']
        exam=medical.save(db,actor,pid,'exams',{'status':'COMPLETED','basis':'OTHER','issued_on':'2026-01-01','number':'PG-GUARD','fitness':'FIT'})['id']
        key=documents.save(db,actor,pid,'other',{'number':'Тест'})
        db.rollback()
        cases=[
            ('DELETE FROM person_assignments WHERE id=:a',{'a':assignment}),
            ('DELETE FROM staff_versions WHERE id=:v',{'v':version}),
            ('DELETE FROM positions WHERE position_id=:p',{'p':position.position_id}),
            ("UPDATE staff_versions SET valid_to='2026-01-01' WHERE id=:v",{'v':version}),
            ('UPDATE positions SET staff_version_id=999999 WHERE position_id=:p',{'p':position.position_id}),
            ('UPDATE person_medical_exams SET person_id=:q,injury_id=:i WHERE id=:e',{'q':qid,'i':injury,'e':exam}),
            ('UPDATE persons SET birth_day=30,birth_month=2,birth_year=2025 WHERE person_id=:p',{'p':pid}),
            ('UPDATE person_documents SET replaces_id=id WHERE id=:k',{'k':key}),
        ]
        for sql,params in cases:
            with pytest.raises(SQLAlchemyError):
                with db.begin_nested():db.execute(text(sql),params)
        assert db.get(PersonAssignment,assignment) is not None
        assert db.get(Person,pid).birth_day is None


def test_real_deadlock_is_rolled_back_without_automatic_retry(pg_factory):
    from app.database.transactions import service_transaction
    actor,pid,qid=prepare(pg_factory)
    barrier=Barrier(2)
    def change(pair):
        first,second=pair
        with pg_factory() as db:
            try:
                with service_transaction(db):
                    db.execute(text('SELECT person_id FROM persons WHERE person_id=:p FOR UPDATE'),{'p':first})
                    barrier.wait(timeout=5)
                    db.execute(text('SELECT person_id FROM persons WHERE person_id=:p FOR UPDATE'),{'p':second})
                    db.execute(text("UPDATE persons SET personal_number='synthetic deadlock winner' WHERE person_id=:p"),{'p':first})
                return 'saved'
            except ValueError as error:
                assert 'паралельних' in str(error)
                return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(change,[(pid,qid),(qid,pid)]))
    assert sorted(results)==['conflict','saved']

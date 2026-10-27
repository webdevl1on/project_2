"""Display-only abbreviations and editable type hints; synthetic records only."""
from types import SimpleNamespace
import pytest
from app.services.geography import format_address, save, suggestions
from app.geography import SETTLEMENT_TYPES, STREET_TYPES
from app.models import GeoUnit, GeoImportLink, GeoSource
from tests.test_name_cases import factory, client
from tests.test_geography import person,current


def test_requested_full_address_exactly_and_extended_community():
    source={'country':'Україна','region':'Дніпропетровська','district':'Криворізький','community':'Криворізька','settlement_type':'місто','settlement':'Кривий Ріг','street_type':'вулиця','street':'Бруно','house':'01А/2','apartment':'003','note':'Вигаданий навчальний приклад; не є адресою реальної особи'}
    expected='Україна, Дніпропетровська обл., Криворізький р-н, м. Кривий Ріг, вул. Бруно, буд. 01А/2, кв. 003, Вигаданий навчальний приклад; не є адресою реальної особи'
    before=source.copy()
    assert format_address(source)==expected
    assert format_address(SimpleNamespace(**source))==expected
    assert format_address(source,extended=True)==expected.replace('р-н, м.', 'р-н, Криворізька, м.')
    assert source==before


@pytest.mark.parametrize('data,expected',[
 ({'country':'Україна','region':'Львівська область','district':'Тестовий район'},'Україна, Львівська обл., Тестовий р-н'),
 ({'country':'Україна','region':'Львівська обл.','district':'Тестовий р-н'},'Україна, Львівська обл., Тестовий р-н'),
 ({'country':'Україна','district':'Тестовий р-н р-н'},'Україна, Тестовий р-н'),
 ({'settlement_type':'місто','settlement':'Тестове'},'м. Тестове'),
 ({'settlement_type':'село','settlement':'Тестове'},'с. Тестове'),
 ({'settlement_type':'селище','settlement':'Тестове'},'с-ще Тестове'),
 ({'settlement_type':'селище міського типу','settlement':'Тестове'},'смт Тестове'),
 ({'settlement_type':'хутір','settlement':'Тестове'},'х. Тестове'),
 ({'country':'Україна','region':'Київ','settlement_type':'місто','settlement':'Київ'},'Україна, м. Київ'),
 ({'country':'Україна','region':'Севастополь','settlement_type':'місто','settlement':'Севастополь'},'Україна, м. Севастополь'),
 ({'country':'Україна','region':'АР Крим'},'Україна, АР Крим'),
 ({'country':'Україна','region':'Автономна Республіка Крим'},'Україна, Автономна Республіка Крим'),
 ({'country':'Canada','region':'Ontario','district':'York'},'Canada, Ontario, York'),
 ({'country':'Польща','region':'Львівська','district':'Тестовий'},'Польща, Львівська, Тестовий'),
 ({'region':'Львівська область'},'Львівська обл.'),
 ({'region':'California'},'California'),
 ({'community':'Єдина відома громада'},'Єдина відома громада'),
 ({'settlement_type':'Особливий тип','settlement':'Тестове','street_type':'Історичний шлях','street':'Тестова'},'Особливий тип Тестове, Історичний шлях Тестова'),
 ({'settlement_type':'місто','settlement':'м. Тестове','street_type':'вулиця','street':'вул. Тестова'},'м. Тестове, вул. Тестова'),
 ({'settlement_type':'місто','settlement':'м.Тестове','street_type':'вулиця','street':'вулиця Тестова'},'м. Тестове, вул. Тестова'),
 ({'settlement_type':'місто','settlement':'місто м. Тестове'},'м. Тестове'),
 ({'street_type':'проспект','street':'Тестовий'},'просп. Тестовий'),
 ({'house':'01А/2','corps':'2-Б','apartment':'003','room':'02'},'буд. 01А/2, корп. 2-Б, кв. 003, кімн. 02'),
 ({'country':None,'region':'','street':None},''),
])
def test_address_components(data,expected):
    assert format_address(data)==expected


@pytest.mark.parametrize('full,abbr',STREET_TYPES.items())
def test_all_explicit_street_types(full,abbr):
    assert format_address({'street_type':full,'street':'Тестова'})==f'{abbr} Тестова'


def test_custom_types_and_history_are_never_rewritten(factory):
    with factory() as db:
        pid=person(db)
        save(db,pid,'registration',{'settlement':'Тестове','settlement_type':'Особливий тип','street':'Тестова','street_type':'Давній шлях'})
        old=current(db,pid)
        save(db,pid,'registration',{'record_id':str(old.id),'revision':str(old.revision),'street_type':'проспект','street':'Нова'})
        db.refresh(old)
        assert not old.is_active and old.street_type=='Давній шлях'
        assert format_address(old)=='Особливий тип Тестове, Давній шлях Тестова'
        assert old.settlement_type=='Особливий тип'


@pytest.mark.parametrize('kind,raw,expected,other',[('settlement','village','село','city'),('street','проспект','проспект','вулиця')])
def test_type_suggestions_only_when_import_metadata_is_unambiguous(factory,kind,raw,expected,other):
    with factory() as db:
        source=GeoSource(id='test',metadata_json={}); unit=GeoUnit(kind=kind,name='Тестове',normalized_name='тестове')
        db.add_all([source,unit]);db.flush()
        assert suggestions(db,kind,'Тес')[0]['type'] is None
        db.add(GeoImportLink(kind=kind,external_id='first',unit_id=unit.id,source_id='test',source_version='test',package_digest='0'*64,details={kind+'_type':raw}));db.commit()
        assert suggestions(db,kind,'Тес')[0]['type']==expected
        db.add(GeoImportLink(kind=kind,external_id='second',unit_id=unit.id,source_id='test',source_version='test',package_digest='0'*64,details={kind+'_type':other}));db.commit()
        assert suggestions(db,kind,'Тес')[0]['type'] is None

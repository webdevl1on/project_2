"""Editor metadata reuses lifecycle; all data are synthetic and isolated."""
from app.models import DocumentType,PersonDocument,DocumentFile
from app.services import documents,document_files
from app.services.document_storage import DocumentStorage
from tests.test_documents import prepared
from tests.test_name_cases import factory,client


def test_catalog_real_types_trusted_schema_and_canonical_fields(factory,prepared):
    actor,_,_,pid,_=prepared
    with factory() as db:
        db.add(DocumentType(code='custom-note',name='Тестовий додатковий документ',schema_key='other',is_primary=False));db.commit()
        catalog=documents.editor_catalog(db,actor,pid)
        assert len(catalog['types'])==9
        custom=next(t for t in catalog['types'] if t['code']=='custom-note')
        assert custom['name']=='Тестовий додатковий документ' and custom['schema']['fields']
        passport=next(t for t in catalog['types'] if t['code']=='passport')
        policies=[f for f in passport['schema']['fields'] if f['kind']=='partial_date']
        assert [f['key'] for f in policies]==['issued','expire'] and all(f['policy']['allow_partial'] for f in policies)
        assert next(t for t in catalog['types'] if t['code']=='tax_number')['schema']['fields'][0]['kind']=='text'
        assert all(f['kind']!='partial_date' for t in catalog['types'] if t['code']!='passport' for f in t['schema']['fields'])


def test_listing_editor_fields_and_files_keep_independent_states(factory,prepared,tmp_path):
    actor,_,_,pid,_=prepared
    with factory() as db:
        key=documents.save(db,actor,pid,'other',{})
        file=document_files.attach(db,actor,pid,key,db.get(PersonDocument,key).revision,b'%PDF-1.7 synthetic','page.pdf','page',storage=DocumentStorage(tmp_path/'copies'))
        row=next(r for r in documents.list_documents(db,actor,pid) if r['id']==key)
        assert row['type_name']=='Інший документ' and row['schema_key']=='other' and not row['is_primary']
        assert row['presence']=='UNKNOWN' and row['automatic_status']=='NOT_FILLED' and row['has_copies']
        assert row['files'][0]['revision']==db.get(DocumentFile,file).revision and row['files'][0]['side']=='page'


def test_catalog_api_access_and_cache_policy(client,prepared):
    browser,_=client;pid=prepared[3]
    assert browser.get(f'/persons/{pid}/documents/catalog').status_code in (401,403)
    assert browser.post('/auth/login',json={'username':'admin','password':'test-password-123'}).status_code==200
    result=browser.get(f'/persons/{pid}/documents/catalog')
    assert result.status_code==200 and result.headers['cache-control']=='no-store'
    assert len(result.json()['types'])==8 and result.json()['presence']['NEVER_OBTAINED']=='Не отримували'

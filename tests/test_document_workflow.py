"""Isolated canonical tax writes, ordered copies, retry receipts and private viewing."""
from datetime import datetime
from sqlalchemy import select, func
import pytest
from app.models import Person, PersonName, PersonDocument, DocumentDetails, DocumentFile, DocumentAudit
from app.services import documents as docs, document_files as files
from app.services.document_storage import DocumentStorage
from tests.test_name_cases import factory,client
from tests.test_documents import prepared


def test_tax_number_is_narrow_canonical_nullable_unique_and_audited(factory,prepared):
    actor,editor,viewer,pid,other=prepared
    with factory() as db:
        name=PersonName(person_id=pid,surname='Тестенко',name='Тест',surname_latin='Testenko');db.add(name);db.commit()
        key=docs.save(db,actor,pid,'tax_number',{})
        current=db.get(PersonDocument,key)
        result=docs.update_tax_number(db,editor,pid,'0123456789','0000000001',key=key,revision=current.revision)
        assert db.get(Person,pid).tax_number=='0123456789' and name.surname_latin=='Testenko'
        assert db.scalar(select(func.count()).select_from(PersonDocument))==1
        assert db.scalar(select(func.count()).select_from(DocumentDetails))==0
        with pytest.raises(ValueError):docs.update_tax_number(db,actor,pid,'123','0123456789',key=key,revision=result['revision'])
        with pytest.raises(ValueError):docs.update_tax_number(db,actor,pid,'1111111111','0000000001',key=key,revision=result['revision'])
        with pytest.raises(PermissionError):docs.update_tax_number(db,viewer,pid,None,'0123456789',key=key,revision=result['revision'])
        with pytest.raises(ValueError):docs.update_tax_number(db,actor,other,'0123456789',None)
        docs.archive(db,actor,pid,key,result['revision'])
        docs.update_tax_number(db,actor,pid,None,'0123456789')
        archived=next(r for r in docs.list_documents(db,actor,pid) if r['id']==key)
        assert archived['values']['number']=='0123456789'
        assert db.get(Person,pid).tax_number is None
        assert db.scalar(select(DocumentAudit).where(DocumentAudit.operation=='tax_number')).actor_id==editor


def test_order_retry_receipt_side_ownership_revision_and_rollback(factory,prepared,tmp_path,monkeypatch):
    actor,editor,viewer,pid,other=prepared
    store=DocumentStorage(tmp_path/'private')
    with factory() as db:
        key=docs.save(db,actor,pid,'other',{'number':'COPY-1'})
        ids=[];first_rev=db.get(PersonDocument,key).revision
        for n in range(3):
            ids.append(files.attach(db,editor,pid,key,db.get(PersonDocument,key).revision,b'%PDF-1.7 '+bytes([65+n]),f'{n}.pdf','front' if n==0 else 'other',storage=store,request_id=f'upload-request-{n:04d}'))
        assert files.attach(db,editor,pid,key,first_rev,b'%PDF-1.7 A','0.pdf','front',storage=store,request_id='upload-request-0000')==ids[0]
        assert db.scalar(select(func.count()).select_from(DocumentFile))==3
        revision=db.get(PersonDocument,key).revision
        for invalid in [ids[:2],[ids[0]]*3,[*ids[:2],9999]]:
            with pytest.raises(ValueError):files.reorder(db,actor,pid,key,invalid,revision)
        with pytest.raises(ValueError):files.reorder(db,actor,other,key,ids,revision)
        with pytest.raises(PermissionError):files.reorder(db,viewer,pid,key,ids,revision)
        files.reorder(db,editor,pid,key,list(reversed(ids)),revision)
        with pytest.raises(ValueError):files.reorder(db,actor,pid,key,ids,revision)
        rows=next(r for r in docs.list_documents(db,actor,pid) if r['id']==key)['files']
        assert [f['id'] for f in rows]==list(reversed(ids))
        assert db.get(DocumentFile,ids[0]).side=='front'
        def fail(*a,**k):raise ValueError('audit failed')
        monkeypatch.setattr(files,'audit',fail)
        with pytest.raises(ValueError):files.reorder(db,actor,pid,key,ids,db.get(PersonDocument,key).revision)
        assert [f['id'] for f in next(r for r in docs.list_documents(db,actor,pid) if r['id']==key)['files']]==list(reversed(ids))


def test_inline_file_access_and_retained_removed_history(client,factory,prepared,tmp_path,monkeypatch):
    actor,editor,viewer,pid,other=prepared;browser,_=client
    monkeypatch.setenv('PROJECT2_DOCUMENT_STORAGE',str(tmp_path/'private'))
    with factory() as db:
        key=docs.save(db,actor,pid,'other',{})
        fid=files.attach(db,actor,pid,key,db.get(PersonDocument,key).revision,b'\x89PNG\r\n\x1a\nsynthetic','page.png','other')
    url=f'/persons/{pid}/documents/files/{fid}?inline=true'
    assert browser.get(url).status_code==401
    login=browser.post('/auth/login',json={'username':'admin','password':'test-password-123'}).json()
    response=browser.get(url)
    assert response.status_code==200 and response.headers['content-disposition'].startswith('inline')
    assert response.headers['cache-control']=='private, no-store' and response.headers['x-content-type-options']=='nosniff'
    with factory() as db:files.remove(db,actor,pid,fid,db.get(DocumentFile,fid).revision,'тест')
    assert browser.get(url).status_code==409
    assert browser.get(url+'&history=true').status_code==200
    assert browser.get(f'/persons/{other}/documents/files/{fid}?inline=true&history=true').status_code==409


def test_new_apis_require_current_user_csrf_and_matching_tax_revision(client,factory,prepared):
    browser,_=client;actor,editor,viewer,pid,other=prepared
    path=f'/persons/{pid}/documents'
    assert browser.post(path+'/tax-number',json={'number':None,'expected':'0000000001'}).status_code==401
    csrf=browser.post('/auth/login',json={'username':'admin','password':'test-password-123'}).json()['csrf_token']
    with factory() as db:
        key=docs.save(db,actor,pid,'tax_number',{})
        revision=db.get(PersonDocument,key).revision
    body={'number':'0012345678','expected':'0000000001','id':key,'revision':revision}
    assert browser.post(path+'/tax-number',json=body).status_code==403
    assert browser.post(path+'/tax-number',json=body,headers={'X-CSRF-Token':csrf}).status_code==200
    assert browser.post(path+'/tax-number',json=body,headers={'X-CSRF-Token':csrf}).status_code==409
    assert browser.post(path+f'/{key}/files/order',json={'ids':[],'revision':revision}).status_code==403

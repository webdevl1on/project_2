from datetime import date, timedelta
from io import BytesIO
from urllib.parse import urlencode
from fastapi import APIRouter, Depends, Form, File, UploadFile, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services.staff_service import StaffService
from app.services.staff_read import history_context, assignment_preview, position_version_id
from app.services.staff_import import preview_import, import_version
from app.services.staff_tokens import sign, verify, store_preview, load_preview
from app.templating import templates

router=APIRouter()


from app.services.staff_service import domain_date

def failure(error,status=409):
    return JSONResponse({"detail":str(error)},status_code=status)


@router.post('/person-positions/assign/prepare')
def prepare_assignment(position_id:int=Form(),person_id:str=Form(""),on:str=Form(),assignment_order_number:str=Form(""),assignment_order_date:str=Form(""),transfer_release_order_number:str=Form(""),transfer_release_order_date:str=Form(""),db:Session=Depends(get_db)):
    try:
        person=int(person_id) if person_id else None
        snapshot,options,target,source,previous=assignment_preview(db,position_id,person,domain_date(on))
        from app.services.staff_service import order_values
        order=order_values(assignment_order_number,domain_date(assignment_order_date,False))
        release=order_values(transfer_release_order_number,domain_date(transfer_release_order_date,False),'release')
        if any([*order.values(),*release.values()]): snapshot['orders']={'number':order['assignment_order_number'],'date':order['assignment_order_date'].isoformat() if order['assignment_order_date'] else None,'release_number':release['release_order_number'],'release_date':release['release_order_date'].isoformat() if release['release_order_date'] else None}
        label=next((item['label'] for item in options if item['id']==person),'Військовослужбовець')
        transfer=bool(source and source.staff_position_id!=position_id)
        noop=bool(source and snapshot['source']==snapshot['target'])
        message=(f"{label} уже призначений на посаду № {previous.position_number}. Перепризначити на посаду № {target.position_number} із {on}?"
                 if transfer else 'Підтвердьте завершення призначення.' if person is None else 'Призначення перевірено.')
        if transfer:message+=f" Попереднє призначення буде завершено {(domain_date(on)-timedelta(days=1)).isoformat()}."
        return {"token":sign(snapshot,'assignment'),"requires_confirmation":transfer or (person is None and bool(snapshot['target'])),
                "message":message,"noop":noop}
    except ValueError as error:return failure(error)


@router.post('/person-positions/assign')
def assign(token:str=Form(),confirmed:bool=Form(False),return_query:str=Form(""),db:Session=Depends(get_db)):
    try:
        snapshot=verify(token,'assignment')
        message=StaffService.assign(db,snapshot['position_id'],snapshot['person_id'],date.fromisoformat(snapshot['on']),snapshot,confirmed)
        # A fixed local path; query text is never interpreted as a redirect URL.
        return RedirectResponse('/person-positions?'+return_query.lstrip('?')+'&'+urlencode({'staff_message':message}),303)
    except ValueError as error:return failure(error)


@router.post('/staff/import/preview')
async def import_preview(request:Request,file:UploadFile=File(),name:str=Form(),valid_from:str=Form(),
                         valid_to:str=Form(""),current:bool=Form(False),structure_id:str=Form(""),db:Session=Depends(get_db)):
    try:
        if not (file.filename or '').lower().endswith('.xlsx'):raise ValueError("Оберіть файл .xlsx.")
        data=await file.read(5*1024*1024+1)
        if len(data)>5*1024*1024:raise ValueError("Файл перевищує 5 МБ.")
        prepared=preview_import(db,BytesIO(data),int(structure_id) if structure_id else None,name,
                                domain_date(valid_from),domain_date(valid_to,False),current)
        token=store_preview(prepared) if not prepared['errors'] else None
        return templates.TemplateResponse(request=request,name='staff_import_preview.html',context={'preview':prepared,'token':token})
    except (ValueError,TypeError) as error:
        return templates.TemplateResponse(request=request,name='staff_import_preview.html',context={'preview':{'errors':[str(error)],'warnings':[]},'token':None},status_code=400)
    finally:await file.close()


@router.post('/staff/import/confirm')
def import_confirm(request:Request,token:str=Form(),db:Session=Depends(get_db)):
    try:
        prepared,key=load_preview(token)
        version=import_version(db,prepared,key)
        return RedirectResponse('/person-positions?'+urlencode({'version_id':version,'as_of':prepared['start'],'staff_message':f"Завантажено {len(prepared['positions'])} посад. Усі посади вакантні."}),303)
    except ValueError as error:
        return templates.TemplateResponse(request=request,name='staff_import_preview.html',context={'preview':{'errors':[str(error)],'warnings':[]},'token':None},status_code=409)


@router.get('/staff/history')
def history(request:Request,version_id:int|None=None,db:Session=Depends(get_db)):
    context=history_context(db,version_id)
    from app.table_fields import FIELDS
    position_fields=[{'key':field.attribute,'label':field.label} for field in FIELDS.values() if field.source=='position']
    return templates.TemplateResponse(request=request,name='staff_history.html',context={
        **context,'position_fields':position_fields,'message':request.query_params.get('message','')})


def form_failure(request,error):
    if 'application/json' in request.headers.get('accept',''):
        message=str(error)
        fields=[]
        constraint=str(getattr(error.__cause__,'orig',''))
        if 'UNIQUE constraint failed: positions.staff_version_id, positions.position_number' in constraint:
            message='Посада з таким номером уже існує у цій версії штату.'
            fields=['position_number']
        elif 'UNIQUE constraint failed: staff_versions.staff_structure_id, staff_versions.name' in constraint:
            message='Версія з такою назвою вже існує у цій структурі.'
            fields=['name']
        elif 'UNIQUE constraint failed: staff_structures.code' in constraint:
            message='Структура з таким кодом уже існує.'
            fields=['code']
        elif 'Завершення не може передувати початку' in message:
            message='Дата завершення не може бути раніше дати початку.'
            fields=['assigned_to'] if '/assignments/' in request.url.path else ['valid_to']
        elif 'перетинаються' in message or 'період' in message.lower():
            fields=['assigned_from','assigned_to','position_id'] if '/assignments/' in request.url.path else ['valid_from','valid_to']
        elif 'змінився' in message or 'блокування' in message:
            message+=' Введені значення збережено у формі.'
        return JSONResponse({'detail':message,'fields':fields},status_code=409)
    return templates.TemplateResponse(request=request,name='staff_error.html',context={'error':str(error)},status_code=409)


@router.post('/staff/structures')
def create_structure(request:Request,code:str=Form(),name:str=Form(),db:Session=Depends(get_db)):
    try:
        StaffService.create_structure(db,code,name)
        return RedirectResponse('/staff/history?'+urlencode({'message':'Структуру створено.'}),303)
    except ValueError as error:return form_failure(request,error)


@router.post('/staff/versions/{key}/close')
def close_version(request:Request,key:int,revision:int=Form(),valid_to:str=Form(),confirmed:bool=Form(False),db:Session=Depends(get_db)):
    try:
        if not confirmed:raise ValueError('Підтвердьте явне закриття версії та її призначень.')
        StaffService.close_version(db,key,revision,domain_date(valid_to))
        return RedirectResponse('/staff/history?'+urlencode({'version_id':key,'message':'Версію та всі її відкриті призначення завершено.'}),303)
    except ValueError as error:return form_failure(request,error)


@router.post('/staff/versions/{key}/correct')
def correct_version(request:Request,key:int,revision:int=Form(),name:str=Form(),valid_from:str=Form(),valid_to:str=Form(''),db:Session=Depends(get_db)):
    try:
        StaffService.correct_version(db,key,revision,name,domain_date(valid_from),domain_date(valid_to,False))
        return RedirectResponse('/staff/history?'+urlencode({'version_id':key,'message':'Реквізити версії виправлено.'}),303)
    except ValueError as error:return form_failure(request,error)


@router.post('/staff/assignments/create')
def create_assignment(request:Request,person_id:int=Form(),position_id:int=Form(),assigned_from:str=Form(),assigned_to:str=Form(''),assignment_order_number:str=Form(''),assignment_order_date:str=Form(''),db:Session=Depends(get_db)):
    try:
        StaffService.create_assignment(db,person_id,position_id,domain_date(assigned_from),domain_date(assigned_to,False),order_number=assignment_order_number,order_date=domain_date(assignment_order_date,False))
        return RedirectResponse('/staff/history?'+urlencode({'version_id':position_version_id(db,position_id),'message':'Призначення збережено.'}),303)
    except ValueError as error:return form_failure(request,error)


@router.post('/staff/assignments/{key}/correct')
def correct_assignment(request:Request,key:int,revision:int=Form(),person_id:int=Form(),position_id:int=Form(),assigned_from:str=Form(),assigned_to:str=Form(''),db:Session=Depends(get_db)):
    try:
        StaffService.correct_assignment(db,key,revision,person_id,position_id,domain_date(assigned_from),domain_date(assigned_to,False))
        return RedirectResponse('/staff/history?'+urlencode({'version_id':position_version_id(db,position_id),'message':'Призначення збережено.'}),303)
    except ValueError as error:return form_failure(request,error)


@router.post('/staff/positions/{key}/correct')
async def correct_position(request:Request,key:int,db:Session=Depends(get_db)):
    try:
        from app.services.staff_service import POSITION_ATTRIBUTES
        form=await request.form()
        values={name:form[name] for name in POSITION_ATTRIBUTES if name in form}
        StaffService.correct_position(db,key,int(form['revision']),values)
        return RedirectResponse('/staff/history?'+urlencode({'version_id':position_version_id(db,key),'message':'Реквізити посади виправлено.'}),303)
    except (ValueError,KeyError) as error:return form_failure(request,error)

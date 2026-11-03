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
from app.security.accounts import personal_actor

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
def assign(request:Request,token:str=Form(),confirmed:bool=Form(False),return_query:str=Form(""),db:Session=Depends(get_db)):
    try:
        snapshot=verify(token,'assignment')
        message=StaffService.assign(db,snapshot['position_id'],snapshot['person_id'],date.fromisoformat(snapshot['on']),snapshot,confirmed,actor_id=personal_actor(request,db))
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
        return RedirectResponse('/admin/staff?'+urlencode({'version_id':version,'message':f"Завантажено {len(prepared['positions'])} посад. Усі посади вакантні."}),303)
    except ValueError as error:
        return templates.TemplateResponse(request=request,name='staff_import_preview.html',context={'preview':{'errors':[str(error)],'warnings':[]},'token':None},status_code=409)


@router.get('/staff/history')
def history(request:Request,version_id:int|None=None,q:str='',db:Session=Depends(get_db)):
    context=history_context(db,version_id,search=q)
    return templates.TemplateResponse(request=request,name='staff_history.html',context={
        **context,'message':request.query_params.get('message','')})


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
        elif 'завтра' in message:
            fields=['assigned_from']
        elif 'Причина анулювання' in message:
            fields=['reason']
        elif 'перетинаються' in message or 'період' in message.lower():
            fields=['assigned_from','assigned_to','position_id'] if '/assignments/' in request.url.path else ['valid_from','valid_to']
        elif 'змінився' in message or 'блокування' in message:
            message+=' Введені значення збережено у формі.'
        return JSONResponse({'detail':message,'fields':fields},status_code=409)
    return templates.TemplateResponse(request=request,name='staff_error.html',context={'error':str(error)},status_code=409)


@router.post('/staff/structures')
def create_structure(request:Request,code:str=Form(),name:str=Form(),db:Session=Depends(get_db)):
    try:
        key=StaffService.create_structure(db,code,name)
        return RedirectResponse('/admin/staff?'+urlencode({'structure_id':key,'message':'Структуру створено.'}),303)
    except ValueError as error:return form_failure(request,error)


@router.post('/staff/versions/{key}/close')
def close_version(request:Request,key:int,revision:int=Form(),valid_to:str=Form(),confirmed:bool=Form(False),db:Session=Depends(get_db)):
    try:
        if not confirmed:raise ValueError('Підтвердьте явне закриття версії та її призначень.')
        StaffService.close_version(db,key,revision,domain_date(valid_to),actor_id=personal_actor(request,db))
        return RedirectResponse('/admin/staff?'+urlencode({'version_id':key,'message':'Версію та всі її відкриті призначення завершено.'}),303)
    except ValueError as error:return form_failure(request,error)


@router.post('/staff/versions/{key}/correct')
def correct_version(request:Request,key:int,revision:int=Form(),name:str=Form(),valid_from:str=Form(),valid_to:str=Form(''),db:Session=Depends(get_db)):
    try:
        StaffService.correct_version(db,key,revision,name,domain_date(valid_from),domain_date(valid_to,False))
        return RedirectResponse('/admin/staff?'+urlencode({'version_id':key,'message':'Реквізити версії виправлено.'}),303)
    except ValueError as error:return form_failure(request,error)


def assignment_details(data):
    return {key: domain_date(data.get(key), False) if key.endswith('_date') else data.get(key)
            for key in ('assignment_order_number','assignment_order_date','release_order_number',
                        'release_order_date','completion_reason','completion_note')}


def history_redirect(db, position_id, data, message='Призначення збережено.'):
    return RedirectResponse('/staff/history?'+urlencode({'version_id':position_version_id(db,position_id),
        'q':data.get('q',''),'message':message})+'#position-'+str(position_id),303)


@router.post('/staff/assignments/create')
async def create_assignment(request:Request,db:Session=Depends(get_db)):
    try:
        data=dict(await request.form()); details=assignment_details(data)
        position_id=int(data['position_id'])
        StaffService.create_assignment(db,int(data['person_id']),position_id,
            domain_date(data.get('assigned_from')),domain_date(data.get('assigned_to'),False),
            order_number=details['assignment_order_number'],order_date=details['assignment_order_date'],
            release_number=details['release_order_number'],release_date=details['release_order_date'],
            completion_reason=details['completion_reason'],completion_note=details['completion_note'],
            actor_id=personal_actor(request,db))
        return history_redirect(db,position_id,data)
    except (ValueError,KeyError) as error:return form_failure(request,error)


@router.post('/staff/assignments/prepare')
async def prepare_history(request:Request,db:Session=Depends(get_db)):
    try:
        personal_actor(request,db)
        data=dict(await request.form()); details=assignment_details(data)
        start=domain_date(data.get('assigned_from'));end=domain_date(data.get('assigned_to'),False)
        from app.services.staff_service import period, order_values, completion_values
        period(start,end)
        position_id=int(data['position_id']);person_id=int(data['person_id'])
        snapshot,options,target,source,previous=assignment_preview(db,position_id,person_id,start)
        order_values(details['assignment_order_number'],details['assignment_order_date'])
        release=order_values(data.get('transfer_release_order_number'),domain_date(data.get('transfer_release_order_date'),False),'release')
        snapshot['orders']={'number':details['assignment_order_number'],'date':details['assignment_order_date'].isoformat() if details['assignment_order_date'] else None,
            'release_number':release['release_order_number'],'release_date':release['release_order_date'].isoformat() if release['release_order_date'] else None}
        completion=completion_values(details['release_order_number'],details['release_order_date'],details['completion_reason'],details['completion_note'])
        snapshot['end']=end.isoformat() if end else None
        snapshot['completion']={'number':completion['release_order_number'],'issued':completion['release_order_date'].isoformat() if completion['release_order_date'] else None,'reason':completion['completion_reason'],'note':completion['completion_note']}
        transfer=bool(source and source.staff_position_id!=position_id)
        from app.utils.date_utils import format_calendar_date as format_date
        message=(f'Попередня посада №{previous.position_number} — {previous.name_short}. Останній день: {format_date(start-timedelta(days=1))}. '
                 f'Нова посада №{target.position_number} — {target.name_short}, з {format_date(start)}. Підтвердьте переведення.' if transfer else 'Призначення перевірено.')
        return {'token':sign(snapshot,'assignment'),'requires_confirmation':transfer,'message':message,'noop':bool(source and snapshot['source']==snapshot['target'])}
    except (ValueError,KeyError) as error:return form_failure(request,error)


@router.post('/staff/assignments/confirm')
async def confirm_history(request:Request,db:Session=Depends(get_db)):
    try:
        data=dict(await request.form());payload=verify(data.get('token',''),'assignment')
        StaffService.assign(db,payload['position_id'],payload['person_id'],domain_date(payload['on']),payload,
                            data.get('confirmed')=='true',actor_id=personal_actor(request,db))
        return history_redirect(db,payload['position_id'],data)
    except (ValueError,KeyError) as error:return form_failure(request,error)


@router.post('/staff/assignments/{key}/correct')
async def correct_assignment(request:Request,key:int,db:Session=Depends(get_db)):
    try:
        data=dict(await request.form());position_id=int(data['position_id'])
        StaffService.correct_assignment(db,key,int(data['revision']),int(data['person_id']),position_id,
            domain_date(data.get('assigned_from')),domain_date(data.get('assigned_to'),False),
            details=assignment_details(data),actor_id=personal_actor(request,db))
        return history_redirect(db,position_id,data)
    except (ValueError,KeyError) as error:return form_failure(request,error)


@router.post('/staff/assignments/{key}/annul')
@router.post('/staff/assignments/{key}/restore')
async def change_assignment_state(request:Request,key:int,db:Session=Depends(get_db)):
    try:
        data=dict(await request.form());actor=personal_actor(request,db)
        if request.url.path.endswith('/annul'):
            StaffService.annul_assignment(db,key,int(data['revision']),data.get('reason'),confirmed=data.get('confirmed')=='on',actor_id=actor)
            message='Призначення анульовано. Історію збережено.'
        else:
            StaffService.restore_assignment(db,key,int(data['revision']),actor_id=actor)
            message='Призначення відновлено.'
        from app.services.staff_read import assignment_position_id
        return history_redirect(db,assignment_position_id(db,key),data,message)
    except (ValueError,KeyError) as error:return form_failure(request,error)


@router.post('/staff/positions/{key}/correct')
async def correct_position(request:Request,key:int,db:Session=Depends(get_db)):
    try:
        from app.services.staff_service import POSITION_ATTRIBUTES
        form=await request.form()
        values={name:form[name] for name in POSITION_ATTRIBUTES if name in form}
        StaffService.correct_position(db,key,int(form['revision']),values)
        return RedirectResponse('/admin/staff?'+urlencode({'version_id':position_version_id(db,key),'message':'Реквізити посади виправлено.'}),303)
    except (ValueError,KeyError) as error:return form_failure(request,error)


@router.get('/staff/assignments/{key}/audit')
def assignment_audit(request:Request,key:int,db:Session=Depends(get_db)):
    from app.services.staff_read import assignment_audit_context
    try:
        return templates.TemplateResponse(request=request,name='components/assignment_audit.html',context=assignment_audit_context(db,key))
    except ValueError as error:return failure(error,404)

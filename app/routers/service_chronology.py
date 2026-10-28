"""Personnel operations share StaffService; never duplicate assignment writes."""
from fastapi import APIRouter,Request,Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import service_chronology as service
from app.services.staff_service import StaffService
from app.services.staff_service import domain_date
router=APIRouter()

@router.post('/persons/{person_id}/personal-number')
async def personal_number(request:Request,person_id:int,db:Session=Depends(get_db)):
    try:
        data=await request.form();service.change_personal_number(db,person_id,data.get('personal_number'))
        return {'ok':True}
    except ValueError as error:return JSONResponse({'detail':str(error)},status_code=409)

@router.post('/persons/{person_id}/service-history')
@router.post('/persons/{person_id}/service-history/{key}')
async def historical(request:Request,person_id:int,key:int|None=None,db:Session=Depends(get_db)):
    try:
        service.save_historical(db,person_id,dict(await request.form()),key);return {'ok':True}
    except ValueError as error:return JSONResponse({'detail':str(error)},status_code=409)

@router.post('/personnel/assignments/{key}/{action}')
async def assignment(request:Request,key:int,action:str,db:Session=Depends(get_db)):
    try:
        data=dict(await request.form());revision=int(data['revision'])
        if action=='orders':
            values={}
            for prefix in ('assignment','release'):
                for suffix in ('number','date'):
                    field=prefix+'_order_'+suffix
                    if field in data:values[prefix+'_'+suffix]=domain_date(data[field],False) if suffix=='date' else data[field]
            StaffService.correct_orders(db,key,revision,**values)
        elif action=='release':StaffService.release_assignment(db,key,revision,domain_date(data.get('release_effective')),data.get('release_order_number'),domain_date(data.get('release_order_date'),False),data.get('note'),data.get('confirmed')=='on')
        elif action=='period':StaffService.correct_assignment(db,key,revision,int(data['person_id']),int(data['position_id']),domain_date(data.get('assigned_from')),domain_date(data.get('assigned_to'),False))
        else:raise ValueError('Невідома дія.')
        return {'ok':True}
    except (ValueError,KeyError) as error:return JSONResponse({'detail':str(error)},status_code=409)

@router.post('/personnel/mirages')
async def create_mirage(request:Request,db:Session=Depends(get_db)):
    from app.services import mirage
    try:
        data=dict(await request.form());mirage.create(db,int(data['person_id']),int(data['position_id']),data.get('note'));return {'ok':True}
    except (ValueError,KeyError) as error:return JSONResponse({'detail':str(error)},status_code=409)

@router.post('/personnel/mirages/{key}/{action}')
async def change_mirage(request:Request,key:int,action:str,db:Session=Depends(get_db)):
    from app.services import mirage
    from app.services.staff_service import order_values
    from app.services.staff_tokens import sign,verify
    try:
        data=dict(await request.form())
        if action=='cancel':mirage.cancel(db,key,int(data['revision']),data.get('reason'));return {'ok':True}
        if action=='prepare':
            orders=order_values(data.get('assignment_order_number'),domain_date(data.get('assignment_order_date'),False))
            release=order_values(data.get('transfer_release_order_number'),domain_date(data.get('transfer_release_order_date'),False),'release')
            payload=mirage.preview(db,key,int(data['revision']),domain_date(data.get('on')),{'number':orders['assignment_order_number'],'date':orders['assignment_order_date'].isoformat() if orders['assignment_order_date'] else None,'release_number':release['release_order_number'],'release_date':release['release_order_date'].isoformat() if release['release_order_date'] else None})
            snapshot=payload['snapshot'];message=f"Оформити офіційне призначення з {snapshot['on']}?"
            if snapshot['source']:message+=' Попереднє призначення буде завершено попереднім календарним днем; обидва записи залишаться в історії.'
            return {'token':sign(payload,'mirage'),'message':message}
        if action=='convert':
            payload=verify(data['token'],'mirage')
            if payload['id']!=key:raise ValueError('Підтвердження належить іншому Міражу.')
            mirage.convert(db,payload,data.get('confirmed')=='on');return {'ok':True}
        raise ValueError('Невідома дія.')
    except (ValueError,KeyError) as error:return JSONResponse({'detail':str(error)},status_code=409)

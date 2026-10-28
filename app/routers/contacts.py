"""HTTP adapter for contact mutations and live profile fragments."""
from fastapi import APIRouter,Request,Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services import contacts
from app.services.person_read import full_profile
from app.templating import templates
router=APIRouter()

@router.get('/persons/{person_id}/contacts')
def contact_list(request:Request,person_id:int,db:Session=Depends(get_db)):
    return templates.TemplateResponse(request=request,name='person/components/contacts.html',context=contacts.page(db,person_id),headers={'Cache-Control':'no-store'})

@router.get('/persons/{person_id}/overview')
def overview(request:Request,person_id:int,db:Session=Depends(get_db)):
    return templates.TemplateResponse(request=request,name='person/components/profile_overview.html',context=full_profile(db,person_id),headers={'Cache-Control':'no-store'})

@router.post('/persons/{person_id}/contacts')
@router.post('/persons/{person_id}/contacts/{key}')
async def write(request:Request,person_id:int,key:int|None=None,db:Session=Depends(get_db)):
    try:contacts.mutate(db,person_id,dict(await request.form()),key)
    except ValueError as error:
        return JSONResponse({'error':str(error),'field':getattr(error,'field','value')},status_code=400,headers={'Cache-Control':'no-store'})
    return JSONResponse({'ok':True},headers={'Cache-Control':'no-store'})

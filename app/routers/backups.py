"""Backup status and durable job requests. There is deliberately no HTTP restore/download."""
from fastapi import APIRouter,Depends,HTTPException,Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.security.accounts import current_user
from app.services.backups import commands
from app.templating import templates
router=APIRouter(prefix='/admin/backups',tags=['Backups'])

@router.get('')
def page(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    return templates.TemplateResponse(request=request,name='admin/backups.html',context={'backup_status':commands.status(db,user.id)})

@router.get('/data')
def status(user=Depends(current_user),db:Session=Depends(get_db)):
    return commands.status(db,user.id)

@router.post('/create')
@router.post('/verify/{identity}')
def enqueue(request:Request,identity:str|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    try:return JSONResponse(commands.enqueue(db,user.id,'verify' if identity else 'create',identity),status_code=202)
    except PermissionError:raise
    except (ValueError,KeyError,TypeError,OSError):raise HTTPException(409,'Завдання відхилено. Перевірте налаштування worker та копії на сервері.') from None

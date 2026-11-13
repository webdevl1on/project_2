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

@router.get('/volumes')
def volumes(user=Depends(current_user),db:Session=Depends(get_db)):
    try:return commands.volumes(db,user.id)
    except ValueError as error:raise HTTPException(409,'USB недоступний. Перевірте локальне підключення до Windows-сервера, список дозволених носіїв та BitLocker.') from None

@router.post('/emergency')
@router.post('/statistics')
@router.post('/usb')
async def maintenance(request:Request,user=Depends(current_user),db:Session=Depends(get_db)):
    operation=request.url.path.rsplit('/',1)[-1]
    try:
        details=await request.json() if operation=='usb' else None
        return JSONResponse(commands.enqueue(db,user.id,operation,details=details),status_code=202)
    except PermissionError:raise
    except (ValueError,KeyError,TypeError,OSError):raise HTTPException(409,'Завдання відхилено. Перевірте захищені каталоги, носій і налаштування worker.') from None

@router.post('/create')
@router.post('/verify/{identity}')
def enqueue(request:Request,identity:str|None=None,user=Depends(current_user),db:Session=Depends(get_db)):
    try:return JSONResponse(commands.enqueue(db,user.id,'verify' if identity else 'create',identity),status_code=202)
    except PermissionError:raise
    except (ValueError,KeyError,TypeError,OSError):raise HTTPException(409,'Завдання відхилено. Перевірте налаштування worker та копії на сервері.') from None

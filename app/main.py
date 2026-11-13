from fastapi import FastAPI, Depends, Request
from app.security.application import application_access
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR

from app.routers import persons
from app.routers import person_name
from app.routers import person_rank
from app.routers import person_positions


from app.database.maintenance import application_lifespan
app = FastAPI(lifespan=application_lifespan, dependencies=[Depends(application_access)], docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(persons.router)
app.include_router(person_name.router)
app.include_router(person_rank.router)
app.include_router(person_positions.router)

from app.routers import staff
app.include_router(staff.router)

from app.routers import name_cases, admin
app.include_router(name_cases.router)
app.include_router(admin.router)

from app.routers import geography
app.include_router(geography.router)
from app.routers import contacts
app.include_router(contacts.router)
from app.routers import service_chronology
app.include_router(service_chronology.router)
from app.routers import service_bases, admin_tcc
app.include_router(service_bases.router)
app.include_router(admin_tcc.router)
from app.routers import accounts, documents
app.include_router(accounts.router)
app.include_router(documents.router)
from app.routers import medical
app.include_router(medical.router)
from app.routers import profile_records
app.include_router(profile_records.router)
from app.routers import person_events
app.include_router(person_events.router)
from app.routers import event_journal
app.include_router(event_journal.router)


@app.middleware('http')
async def private_responses(request: Request, call_next):
    response=await call_next(request)
    if not request.url.path.startswith('/static/'):
        if 'no-store' not in response.headers.get('Cache-Control','').lower():response.headers['Cache-Control']='no-store'
        vary={value.strip() for value in response.headers.get('Vary','').split(',') if value.strip()}
        vary.add('Cookie');response.headers['Vary']=', '.join(sorted(vary))
    return response


@app.get('/openapi.json', include_in_schema=False)
def protected_openapi():
    return app.openapi()


@app.get('/docs', include_in_schema=False)
def protected_docs(request: Request):
    from app.templating import templates
    return templates.TemplateResponse(request=request,name='api_docs.html',context={'api_kind':'swagger'})


@app.get('/redoc', include_in_schema=False)
def protected_redoc(request: Request):
    from app.templating import templates
    return templates.TemplateResponse(request=request,name='api_docs.html',context={'api_kind':'redoc'})

from app.routers import account_management
app.include_router(account_management.router)
from app.routers import mfa
app.include_router(mfa.router)

from app.routers import organization
app.include_router(organization.router)
from app.routers import organization_staff
app.include_router(organization_staff.router)
from app.routers import access_control
app.include_router(access_control.router)

@app.exception_handler(PermissionError)
async def permission_error(request:Request,error:PermissionError):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':str(error) or 'Недостатньо прав доступу.'},status_code=403)

from app.routers import backups
app.include_router(backups.router)
from app.routers import audit
app.include_router(audit.router)
from app.database.backup_maintenance import MaintenanceUnavailable
@app.exception_handler(MaintenanceUnavailable)
async def maintenance_error(request:Request,error:MaintenanceUnavailable):
    from fastapi.responses import JSONResponse
    return JSONResponse({'detail':str(error)},status_code=503,headers={'Retry-After':'5'})

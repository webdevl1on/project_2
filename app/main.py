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
    from fastapi.openapi.docs import get_swagger_ui_html
    from fastapi.responses import HTMLResponse
    from html import escape
    html=get_swagger_ui_html(openapi_url='/openapi.json',title='project_2 API').body.decode()
    extra=f'<meta name="project2-csrf" content="{escape(request.state.csrf_token)}"><script src="/static/js/security_session.js"></script>'
    return HTMLResponse(html.replace('</head>',extra+'</head>'))


@app.get('/redoc', include_in_schema=False)
def protected_redoc():
    from fastapi.openapi.docs import get_redoc_html
    return get_redoc_html(openapi_url='/openapi.json',title='project_2 API')

from app.routers import account_management
app.include_router(account_management.router)
from app.routers import mfa
app.include_router(mfa.router)

from app.routers import organization
app.include_router(organization.router)
from app.routers import organization_staff
app.include_router(organization_staff.router)

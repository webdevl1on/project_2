from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR

from app.routers import persons
from app.routers import person_name
from app.routers import person_rank
from app.routers import person_positions


from app.database.maintenance import application_lifespan
app = FastAPI(lifespan=application_lifespan)
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

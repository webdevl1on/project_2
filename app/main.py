from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import BASE_DIR

from app.routers import persons
from app.routers import person_name
from app.routers import person_rank
from app.routers import person_service
from app.routers import person_positions


app = FastAPI()
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(persons.router)
app.include_router(person_name.router)
app.include_router(person_rank.router)
#app.include_router(person_service.router)
app.include_router(person_positions.router)

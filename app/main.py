from fastapi import FastAPI

from app.routers import persons
from app.routers import person_name
from app.routers import person_rank
from app.routers import person_service
from app.routers import person_positions


app = FastAPI()

app.include_router(persons.router)
app.include_router(person_name.router)
app.include_router(person_rank.router)
#app.include_router(person_service.router)
app.include_router(person_positions.router)
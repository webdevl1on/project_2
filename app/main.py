from fastapi import FastAPI
from app.routers.persons import router as persons_router

app = FastAPI(
    title="Project 2.0"
)

app.include_router(persons_router)

@app.get("/")
def root():
    return {"message": "Project 2.0"}
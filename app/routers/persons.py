from fastapi import APIRouter

router = APIRouter()

@router.get("/persons")
def get_persons():
    return {"status": "ok"}
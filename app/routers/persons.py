from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.person import Person

router = APIRouter()

@router.get("/persons")
def get_persons(db: Session = Depends(get_db)):
    persons = db.query(Person).all()
    return [
        {
            "person_id": person.person_id,
            "pib": person.pib,
            "rank": person.rank,
            "position": person.position,
            "status": person.status,
            "phone": person.phone
        }
        for person in persons
    ]
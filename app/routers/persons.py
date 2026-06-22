from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.person import Person
from datetime import date

router = APIRouter()
templates = Jinja2Templates(
    directory="app/templates"
)

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

@router.get("/persons/{person_id}")
def get_person(person_id: int, db: Session = Depends(get_db)):
    person = (
        db.query(Person)
        .filter(Person.person_id == person_id)
        .first()
    )
    if not person:
        raise HTTPException(
            status_code=404,
            detail="Person not found"
        )
    return [
        {
            "person_id": person.person_id,
            "pib": person.pib,
            "rank": person.rank,
            "position": person.position,
            "status": person.status,
            "phone": person.phone
        }
    ]


@router.post("/persons")
def create_person(
    pib: str,
    rank: str | None,
    birth_date: date | None,
    position: str | None,
    phone: str | None,
    status: str | None,
    db: Session = Depends(get_db)
):

    person = Person(
        pib=pib,
        rank=rank,
        birth_date=birth_date,
        position=position,
        phone=phone,
        status=status,
    )

    db.add(person)
    db.commit()
    db.refresh(person)

    return {
        "message": "Person created",
        "person_id": person.person_id
    }

@router.get("/search")
def search_person(
    request: Request,
    person_id: int | None = None,
    db: Session = Depends(get_db)
):

    person = None

    if person_id:

        person = (
            db.query(Person)
            .filter(Person.person_id == person_id)
            .first()
        )

    return templates.TemplateResponse(
        request=request,
        name="search_person.html",
        context={
            "person": person
        }
    )
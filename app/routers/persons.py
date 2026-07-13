from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.person import Person
from app.models.person_identity import PersonName
from app.models.person_military_service import PersonRank
from app.services.service_common_person_func import CommonPersonFunc


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/persons")
def get_persons_page(request: Request, 
                     sort_by: str = "surname",
                     direction: str = "asc",
                      db: Session = Depends(get_db)):
    sort_columns = {
            "id": Person.person_id,
            "surname": PersonName.surname,
            "name": PersonName.name,
            "birth_date": Person.birth_date,
            "tax_number": Person.tax_number,
            "rank": PersonRank.rank,
        }

    sort_column = sort_columns.get(sort_by, PersonName.surname)

    if direction == "desc":
        order = sort_column.desc()
    else:
        order = sort_column.asc()

    records = (
        db.query(Person, PersonName, PersonRank)
        .outerjoin(
            PersonName,
            and_(
                PersonName.person_id == Person.person_id,
                PersonName.date_to.is_(None),
            ),
        )
        .outerjoin(
            PersonRank,
            and_(
                PersonRank.person_id == Person.person_id,
                PersonRank.date_to.is_(None),
            ),
        )
        .order_by(order, Person.person_id)
        .all()
    )
    persons = [
        {"person": person, 
         "name" : name,
         "rank" : rank,
         }
        for person, name, rank in records
    ]

    return templates.TemplateResponse(
        request=request,
        name="persons.html",
        context={"persons": persons,
                "sort_by": sort_by,
                "direction": direction,},
    )


@router.get("/persons/new")
def get_create_person_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="person_form.html",
        context={"form_data": {}},
    )


@router.post("/persons/new")
def create_person_from_form(
    request: Request,
    surname: Annotated[str, Form()],
    name: Annotated[str, Form()],
    patronymic: Annotated[str | None, Form()] = None,
    tax_number: Annotated[str | None, Form()] = None,
    birth_date: Annotated[str | None, Form()] = None,
    rank: Annotated[str | None, Form()] = None,
    rank_order_number: Annotated[str | None, Form()] = None,
    rank_order_date: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
):
    form_data = {
        "surname": surname,
        "name": name,
        "patronymic": patronymic,
        "surname_latin": None,
        "name_latin": None,
        "patronymic_latin": None,
        "tax_number": tax_number,
        "birth_date": birth_date,
        "rank": rank,
        "rank_order_number": rank_order_number,
        "rank_order_date": rank_order_date,
    }

    try:
        person = CommonPersonFunc.create_person(form_data, db)
    except ValueError as error:
        return templates.TemplateResponse(
            request=request,
            name="person_form.html",
            context={"error": str(error), "form_data": form_data},
            status_code=400,
        )

    return RedirectResponse(url=f"/persons/{person.person_id}", status_code=303)


@router.get("/persons/{person_id}")
def get_person_page(person_id: int, request: Request, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.person_id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    current_name = (
        db.query(PersonName)
        .filter(
            PersonName.person_id == person_id,
            PersonName.date_to.is_(None),
        )
        .first()
    )
    name_history = (
        db.query(PersonName)
        .filter(PersonName.person_id == person_id)
        .order_by(PersonName.date_from.desc())
        .all()
    )
    current_rank = (
        db.query(PersonRank)
        .filter(
            PersonRank.person_id == person_id,
            PersonRank.date_to.is_(None),
        )
        .first()
    )

    return templates.TemplateResponse(
        request=request,
        name="person_detail.html",
        context={
            "person": person,
            "current_name": current_name,
            "name_history": name_history,
            "current_rank": current_rank,
        },
    )

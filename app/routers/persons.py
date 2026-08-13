from typing import Annotated

from urllib.parse import quote
from colorama import reinit
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


def format_form_date(value):
    if not value:
        return ""
    return value.strftime("%d.%m.%Y")


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
                PersonName.is_active.is_(True),
            ),
        )
        .outerjoin(
            PersonRank,
            and_(
                PersonRank.person_id == Person.person_id,
                PersonRank.is_active.is_(True),
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
        context={
            "form_data": {},
            "form_action": "/persons/new",
            "page_title": "Додати людину",
            "submit_label": "Зберегти",
            "cancel_url": "/persons",
        },
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
            context={
                "error": str(error),
                "form_data": form_data,
                "form_action": "/persons/new",
                "page_title": "Додати людину",
                "submit_label": "Зберегти",
                "cancel_url": "/persons",
            },
            status_code=400,
        )

    return RedirectResponse(url=f"/persons/{person.person_id}", status_code=303)


@router.get("/persons/{person_id}/edit")
def get_edit_person_page(person_id: int, request: Request, db: Session = Depends(get_db)):
    person = CommonPersonFunc.get_person_or_raise(person_id, db)
    current_name = (
        db.query(PersonName)
        .filter(
            PersonName.person_id == person_id,
            
        )
        .first()
    )
    current_rank = (
        db.query(PersonRank)
        .filter(
            PersonRank.person_id == person_id,
            
        )
        .first()
    )
    form_data = {
        "surname": current_name.surname if current_name else "",
        "name": current_name.name if current_name else "",
        "patronymic": current_name.patronymic if current_name else "",
        "tax_number": person.tax_number or "",
        "birth_date": format_form_date(person.birth_date),
        "rank": current_rank.rank if current_rank else "",
        "rank_order_number": current_rank.rank_order_number if current_rank else "",
        "rank_order_date": format_form_date(current_rank.rank_order_date) if current_rank else "",
    }

    return templates.TemplateResponse(
        request=request,
        name="person_form.html",
        context={
            "form_data": form_data,
            "form_action": f"/persons/{person_id}/edit",
            "page_title": f"Редагувати людину #{person_id}",
            "submit_label": "Зберегти зміни",
            "cancel_url": f"/person_detail/{person_id}",
        },
    )


@router.post("/persons/{person_id}/edit")
def update_person_from_form(
    person_id: int,
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
        person = CommonPersonFunc.update_person(person_id, form_data, db)
    except ValueError as error:
        return templates.TemplateResponse(
            request=request,
            name="person_form.html",
            context={
                "error": str(error),
                "form_data": form_data,
                "form_action": f"/persons/{person_id}/edit",
                "page_title": f"Редагувати людину #{person_id}",
                "submit_label": "Зберегти зміни",
                "cancel_url": f"/persons/{person_id}",
            },
            status_code=400,
        )

    return RedirectResponse(url=f"/persons/{person.person_id}", status_code=303)


@router.get("/person_detail/{person_id}")
def get_person_page(person_id: int, request: Request, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.person_id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    current_name = (
        db.query(PersonName)
        .filter(
            PersonName.person_id == person_id,
            PersonName.is_active.is_(True),
        )
        .first()
    )
    name_history = (
        db.query(PersonName)
        .filter(PersonName.person_id == person_id)
        .order_by(PersonName.created_at.desc())
        .all()
    )
    current_rank = (
        db.query(PersonRank)
        .filter(
            PersonRank.person_id == person_id,
            PersonRank.is_active.is_(True),
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

# my try
@router.get("/person_full_info/{person_id}")
def get_person_full_info(
    request: Request, 
    person_id: int, 
    db: Session = Depends(get_db),
    error: str | None = None,):
    person = CommonPersonFunc.get_person_or_raise(person_id, db)
    current_name = (
            db.query(PersonName)
            .filter(
                PersonName.person_id == person_id,
                PersonName.is_active.is_(True),
            )
            .first()
        )
    return templates.TemplateResponse(
        request=request,
        name = "person_full_info.html",
        context = {
            "person": person,
            "current_name": current_name,
            "person_id" : person_id,
            "error" : error,
        }
    )

@router.post("/person_name/add_new/{person_id}")
def add_new_name_to_person(
    person_id: int,
    request: Request,
    surname: Annotated[str, Form()],
    name: Annotated[str, Form()],
    patronymic: Annotated[str | None, Form()] = None,
    surname_latin: Annotated[str | None, Form()] = None,
    name_latin: Annotated[str | None, Form()] = None,
    patronymic_latin: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
):
    form_data = {
        "surname": surname,
        "name": name,
        "patronymic": patronymic,
        "surname_latin": surname_latin,
        "name_latin": name_latin,
        "patronymic_latin": patronymic_latin,
    }
    CommonPersonFunc.add_new_name(person_id, form_data, db)
    
    return RedirectResponse(
        url=f"/person_full_info/{person_id}",
        status_code=303,
        )

@router.post("/person_name/{person_name_id}/update")
def update_name_to_person(
    person_name_id: int,
    request: Request,
    surname: Annotated[str, Form()],
    name: Annotated[str, Form()],
    patronymic: Annotated[str | None, Form()] = None,
    surname_latin: Annotated[str | None, Form()] = None,
    name_latin: Annotated[str | None, Form()] = None,
    patronymic_latin: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
):
    form_data = {
        "surname": surname,
        "name": name,
        "patronymic": patronymic,
        "surname_latin": surname_latin,
        "name_latin": name_latin,
        "patronymic_latin": patronymic_latin,
    }

    person_name = CommonPersonFunc.update_person_name(person_name_id, form_data, db)
    
    return RedirectResponse(
        url=f"/person_full_info/{person_name.person_id}",
        status_code=303,
    )

@router.post("/person_name/{person_name_id}/make_active")
def change_name_to_active(
    person_name_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    person_id = CommonPersonFunc.change_person_name_to_active(person_name_id, db)
    return RedirectResponse(
        url=f"/person_full_info/{person_id}",
        status_code=303,
    )

@router.post("/person_name/{person_name_id}/delete")
def delete_person_name(
    person_name_id: int,
    confirmation: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    try:
        person_id = CommonPersonFunc.delete_person_name(
            person_name_id,
            confirmation,
            db,
        )
    except ValueError as error:
        person_name = (
            db.query(PersonName)
            .filter(PersonName.person_name_id == person_name_id)
            .first()
        )
        error_message = quote(str(error))
        
        return RedirectResponse(
            url=f"/person_full_info/{person_name.person_id}?error={error_message}",
            status_code=303,
        )
    return  RedirectResponse(
        url = f"/person_full_info/{person_id}",
        status_code=303,
    )

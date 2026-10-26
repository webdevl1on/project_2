from typing import Annotated
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database.db import get_db
from app.services.service_person_create import ServicePersonCreate
from app.services.person_read import list_people, person_details
from app.templating import templates


router = APIRouter()


def format_form_date(value):
    if not value:
        return ""
    return value.strftime("%d.%m.%Y")

#головна таблиця
@router.get("/persons")
def get_persons_page(request: Request,
                     sort_by: str = "surname",
                     direction: str = "asc",
                     db: Session = Depends(get_db)):
    persons = list_people(db, sort_by, direction)

    return templates.TemplateResponse(
        request=request,
        name="persons.html",
        context={"persons": persons,
                "sort_by": sort_by,
                "direction": direction,},
    )



#Додати нову людину
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


def build_person_form_data(person, current_name):
    return {
        "surname": current_name.surname if current_name else "",
        "name": current_name.name if current_name else "",
        "patronymic": current_name.patronymic if current_name else "",
        "tax_number": person.tax_number or "",
        "birth_day": person.birth_day or "",
        "birth_month": person.birth_month or "",
        "birth_year": person.birth_year or "",
    }


@router.post("/persons/new")
def create_person_from_form(
    request: Request,
    surname: Annotated[str, Form()],
    name: Annotated[str, Form()],
    patronymic: Annotated[str | None, Form()] = None,
    tax_number: Annotated[str | None, Form()] = None,
    birth_day: Annotated[str | None, Form()] = None,
    birth_month: Annotated[str | None, Form()] = None,
    birth_year: Annotated[str | None, Form()] = None,
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
        "birth_day": birth_day,
        "birth_month": birth_month,
        "birth_year": birth_year,
    }

    try:
        person = ServicePersonCreate.create_person(form_data, db)
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
    details = person_details(db, person_id)
    person, current_name = details["person"], details["current_name"]
    return templates.TemplateResponse(
        request=request,
        name="person_form.html",
        context={
            "form_data": build_person_form_data(person, current_name),
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
    birth_day: Annotated[str | None, Form()] = None,
    birth_month: Annotated[str | None, Form()] = None,
    birth_year: Annotated[str | None, Form()] = None,
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
        "birth_day": birth_day,
        "birth_month": birth_month,
        "birth_year": birth_year,
    }

    try:
        person = ServicePersonCreate.update_person(person_id, form_data, db)
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
                "cancel_url": f"/person_detail/{person_id}",
            },
            status_code=400,
        )

    return RedirectResponse(url=f"/person_detail/{person.person_id}", status_code=303)

#Коротка інформація про людину
@router.get("/person_detail/{person_id}")
def get_person_page(person_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        details = person_details(db, person_id, include_history=True)
    except ValueError as error:
        raise HTTPException(status_code=404, detail="Person not found") from error
    return templates.TemplateResponse(
        request=request,
        name="person_detail.html",
        context={
            **details,
        },
    )

#Повна інформація та редагування
@router.get("/person_full_info/{person_id}")
def get_person_full_info(
    request: Request,
    person_id: int,
    db: Session = Depends(get_db),
    ):
    details = person_details(db, person_id, include_ranks=True)
    return templates.TemplateResponse(
        request=request,
        name = "person_full_info.html",
        context = {
            **details,
            "person_id": person_id,
        }
    )

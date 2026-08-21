from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.person_identity import PersonName
from app.services.service_person_name import ServicePersonNameFunc

router = APIRouter(
    prefix="/person_name",
    tags=["Person Name"],
)


@router.post("/add_new/{person_id}")
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
    ServicePersonNameFunc.add_new_name(person_id, form_data, db)
    
    return RedirectResponse(
        url=f"/person_full_info/{person_id}",
        status_code=303,
        )

@router.post("/{person_name_id}/update")
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

    person_name = ServicePersonNameFunc.update_person_name(person_name_id, form_data, db)
    
    return RedirectResponse(
        url=f"/person_full_info/{person_name.person_id}",
        status_code=303,
    )

@router.post("/{person_name_id}/make_active")
def change_name_to_active(
    person_name_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    person_id = ServicePersonNameFunc.change_person_name_to_active(person_name_id, db)
    return RedirectResponse(
        url=f"/person_full_info/{person_id}",
        status_code=303,
    )

@router.post("/{person_name_id}/delete")
def delete_person_name(
    person_name_id: int,
    confirmation: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    try:
        person_id = ServicePersonNameFunc.delete_person_name(
            person_name_id,
            confirmation,
            db,
        )
    except ValueError:
        person_name = (
            db.query(PersonName)
            .filter(PersonName.person_name_id == person_name_id)
            .first()
        )
        if not person_name:
            raise ValueError ("Person name recod was not found")
        return RedirectResponse(
            url=f"/person_full_info/{person_name.person_id}",
            status_code=303,
        )
    return  RedirectResponse(
        url = f"/person_full_info/{person_id}",
        status_code=303,
    )

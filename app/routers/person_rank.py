from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.services.service_person_rank import ServicePersonRankFunc


router = APIRouter(
    prefix="/person_ranks",
    tags=["Person Rank"],
)


def rank_form_data(rank_id, number, exact, day, month, year):
    data = {"rank_id": rank_id, "rank_order_number": number}
    if exact is not None:
        if any(value not in (None, "") for value in (day, month, year)):
            raise ValueError("Передайте або точну дату наказу, або її складові.")
        data["rank_order_date"] = exact
    else:
        data.update(rank_order_day=day, rank_order_month=month, rank_order_year=year)
    return data

#functions for ranks

@router.post("/add_rank/{person_id}")
def add_new_rank_to_person(
    person_id: int,
    request: Request,
    rank_id: Annotated[int, Form()],
    rank_order_number: Annotated[str | None, Form()] = None,
    rank_order_date: Annotated[str | None, Form()] = None,
    rank_order_day: Annotated[str | None, Form()] = None,
    rank_order_month: Annotated[str | None, Form()] = None,
    rank_order_year: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
):

    try:
        form_data = rank_form_data(rank_id, rank_order_number, rank_order_date, rank_order_day, rank_order_month, rank_order_year)
        ServicePersonRankFunc.add_rank(person_id, form_data, db)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return RedirectResponse(
        url=f"/person_full_info/{person_id}",
        status_code=303,
        )

@router.post("/{person_rank_id}/make_active")
def change_rank_to_active(
    person_rank_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    person_id = ServicePersonRankFunc.change_person_rank_to_active(person_rank_id, db)
    return RedirectResponse(
        url=f"/person_full_info/{person_id}",
        status_code=303,
    )

@router.post("/{person_rank_id}/update")
def update_rank_to_person(
    person_rank_id: int,
    request: Request,
    rank_id: Annotated[int, Form()],
    rank_order_number: Annotated[str | None, Form()] = None,
    rank_order_date: Annotated[str | None, Form()] = None,
    rank_order_day: Annotated[str | None, Form()] = None,
    rank_order_month: Annotated[str | None, Form()] = None,
    rank_order_year: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
    ):
    try:
        form_data = rank_form_data(rank_id, rank_order_number, rank_order_date, rank_order_day, rank_order_month, rank_order_year)
        person_rank = ServicePersonRankFunc.update_person_rank(person_rank_id, form_data, db)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return RedirectResponse(
        url=f"/person_full_info/{person_rank.person_id}",
        status_code=303,
    )

@router.post("/{person_rank_id}/delete")
def delete_person_rank(
    person_rank_id: int,
    confirmation: Annotated[str, Form()],
    db: Session = Depends(get_db),
):
    try:
        person_id = ServicePersonRankFunc.delete_person_rank(
            person_rank_id,
            confirmation,
            db,
        )
    except ValueError:
        person_rank = ServicePersonRankFunc.get_record(person_rank_id, db)
        if not person_rank:
            raise ValueError ("Person rank record was not found")
        return RedirectResponse(
            url=f"/person_full_info/{person_rank.person_id}",
            status_code=303,
        )
    return  RedirectResponse(
        url = f"/person_full_info/{person_id}",
        status_code=303,
    )

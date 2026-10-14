from fastapi import APIRouter, Depends, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.reference_book import Position
from app.models.person_positions import PersonPosition
from app.models.person import Person
from app.models.person_identity import PersonName
from app.services.service_person_positions import ServicePersonPositionFunc

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/person-positions")
def get_person_positions_page(
    request: Request,
    unit_short: str | None = None,
    occupancy: str = "all",
    sort_by: str = "position_number",
    direction: str = "asc",
    db: Session = Depends(get_db),
):
    data = ServicePersonPositionFunc.get_positions(
        db=db,
        unit_short=unit_short,
        occupancy=occupancy,
        sort_by=sort_by,
        direction=direction,
    )

    people_records = (
        db.query(Person, PersonName)
        .outerjoin(
            PersonName,
            (PersonName.person_id == Person.person_id)
            & PersonName.is_active.is_(True),
        )
        .order_by(PersonName.surname, PersonName.name)
        .all()
    )

    people = [
        {
            "person": person,
            "name": name,
        }
        for person, name in people_records
    ]

    return templates.TemplateResponse(
        request=request,
        name="person_positions.html",
        context={
            **data,
            "unit_short": unit_short,
            "occupancy": occupancy,
            "sort_by": sort_by,
            "direction": direction,
            "people" : people,
        },
    )

@router.post("/person-positions/assign")
def assign_person_to_position(
    position_id: int = Form(),
    person_id: str = Form(""),
    db: Session = Depends(get_db),
):
    selected_person_id = int(person_id) if person_id else None

    ServicePersonPositionFunc.assign_person_to_position(
        position_id=position_id,
        person_id=selected_person_id,
        db=db,
    )

    return RedirectResponse(
        url="/person-positions",
        status_code=303,
    )
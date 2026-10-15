from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.models.person import Person
from app.models.person_identity import PersonName
from app.services.service_person_positions import FILTER_COLUMNS, ServicePersonPositionFunc


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

FILTER_KEYS = tuple(FILTER_COLUMNS)


def normalise_filter_order(filter_order, column_filters):
    # Older URLs have no explicit order; retain their parameter order as fallback.
    candidates = [*filter_order.split(","), *column_filters]
    return list(dict.fromkeys(
        key for key in candidates if key in FILTER_KEYS and column_filters.get(key)
    ))


def build_query_string(sort_by, direction, occupancy, column_filters, filter_order=""):
    pairs = [("sort_by", sort_by), ("direction", direction), ("occupancy", occupancy)]
    order = normalise_filter_order(filter_order, column_filters)
    pairs.append(("filter_order", ",".join(order)))
    for key in order:
        for value in column_filters.get(key, []):
            pairs.append((key, value))
    return urlencode(pairs)


@router.get("/person-positions")
def get_person_positions_page(
    request: Request,
    occupancy: str = "all",
    sort_by: str = "position_number",
    direction: str = "asc",
    filter_order: str = "",
    position_number: list[str] = Query(default=[]),
    unit_short: list[str] = Query(default=[]),
    name_short: list[str] = Query(default=[]),
    name_nominative: list[str] = Query(default=[]),
    rank: list[str] = Query(default=[]),
    surname: list[str] = Query(default=[]),
    name: list[str] = Query(default=[]),
    patronymic: list[str] = Query(default=[]),
    db: Session = Depends(get_db),
):
    column_filters = {
        "position_number": position_number,
        "unit_short": unit_short,
        "name_short": name_short,
        "name_nominative": name_nominative,
        "rank": rank,
        "surname": surname,
        "name": name,
        "patronymic": patronymic,
    }
    column_filters = {
        key: ServicePersonPositionFunc._normalise_values(column_filters[key])
        for key in dict.fromkeys([*request.query_params.keys(), *FILTER_KEYS])
        if key in FILTER_KEYS
    }
    order = normalise_filter_order(filter_order, column_filters)
    filter_order = ",".join(order)
    sort_by = sort_by if sort_by in FILTER_KEYS else "position_number"
    direction = "desc" if direction == "desc" else "asc"
    occupancy = occupancy if occupancy in ("all", "occupied", "vacant") else "all"
    data = ServicePersonPositionFunc.get_positions(
        db=db,
        occupancy=occupancy,
        sort_by=sort_by,
        direction=direction,
        column_filters=column_filters,
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
    people = [{"person": person, "name": name} for person, name in people_records]

    active_query = build_query_string(sort_by, direction, occupancy, column_filters, filter_order)
    sort_urls = {}
    sort_commands = {}
    for key in FILTER_KEYS:
        next_direction = "desc" if sort_by == key and direction == "asc" else "asc"
        sort_urls[key] = "?" + build_query_string(
            key,
            next_direction,
            occupancy,
            column_filters,
            filter_order,
        )
        sort_commands[key] = {
            value: "?" + build_query_string(key, value, occupancy, column_filters, filter_order)
            for value in ("asc", "desc")
        }

    return templates.TemplateResponse(
        request=request,
        name="person_positions.html",
        context={
            **data,
            "occupancy": occupancy,
            "sort_by": sort_by,
            "direction": direction,
            "active_filters": column_filters,
            "sort_urls": sort_urls,
            "active_query": active_query,
            "filter_order": filter_order,
            "filter_numbers": {key: index + 1 for index, key in enumerate(order)},
            "sort_commands": sort_commands,
            "people": people,
        },
    )


@router.post("/person-positions/assign")
def assign_person_to_position(
    position_id: int = Form(),
    person_id: str = Form(""),
    return_query: str | None = Form(None),
    db: Session = Depends(get_db),
):
    selected_person_id = int(person_id) if person_id else None
    ServicePersonPositionFunc.assign_person_to_position(
        position_id=position_id,
        person_id=selected_person_id,
        db=db,
    )

    url = "/person-positions"
    if return_query:
        url += "?" + return_query.lstrip("?")
    return RedirectResponse(url=url, status_code=303)

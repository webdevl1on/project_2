from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.services.service_person_positions import FILTER_COLUMNS, DATE_FILTER_COLUMNS, SORT_COLUMNS, ServicePersonPositionFunc
from app.table_columns import PERSON_POSITIONS_COLUMNS
from app.utils.date_query import DateFilter, date_priority
from app.utils.date_utils import register_date_globals


router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
register_date_globals(templates.env)

FILTER_KEYS = (*FILTER_COLUMNS, *DATE_FILTER_COLUMNS)
SORT_KEYS = (*SORT_COLUMNS, *DATE_FILTER_COLUMNS)


def normalise_filter_order(filter_order, column_filters):
    # Older URLs have no explicit order; retain their parameter order as fallback.
    candidates = [*filter_order.split(","), *column_filters]
    return list(dict.fromkeys(
        key for key in candidates if key in FILTER_KEYS and column_filters.get(key)
    ))


def build_query_string(sort_by, direction, occupancy, column_filters, filter_order="", priority="year,month,day"):
    pairs = [("sort_by", sort_by), ("direction", direction), ("occupancy", occupancy)]
    order = normalise_filter_order(filter_order, column_filters)
    pairs.append(("filter_order", ",".join(order)))
    priorities = priority if isinstance(priority, dict) else {"birth_date": priority}
    for key in DATE_FILTER_COLUMNS:
        value = priorities.get(key, "year,month,day")
        pairs.append((f"{key}_priority", ",".join(value) if isinstance(value, (list, tuple)) else value))
    for key in order:
        for value in column_filters.get(key, []):
            pairs.append((key, value))
    return urlencode(pairs)


@router.get("/person-positions")
def person_positions_endpoint(request: Request, occupancy: str = "all", sort_by: str = "position_number",
                              direction: str = "asc", filter_order: str = "", db: Session = Depends(get_db)):
    return get_person_positions_page(request, occupancy=occupancy, sort_by=sort_by, direction=direction,
                                     filter_order=filter_order, db=db)


def get_person_positions_page(request, occupancy="all", sort_by="position_number", direction="asc",
                              filter_order="", db=None, **field_values):
    # Read only fields allowed by this table, not arbitrary model attributes.
    column_filters = {key: field_values.get(key, request.query_params.getlist(key)) for key in FILTER_KEYS}
    try:
        priorities = {key: date_priority(field_values.get(f"{key}_priority", request.query_params.get(f"{key}_priority", "year,month,day")))
                      for key in DATE_FILTER_COLUMNS}
        date_filters = {}
        for key in DATE_FILTER_COLUMNS:
            raw_date = column_filters[key] if isinstance(column_filters[key], list) else []
            if len(raw_date) > 1:
                raise ValueError("Фільтр дати має бути заданий один раз.")
            spec = DateFilter.from_json(raw_date[0]) if raw_date else DateFilter()
            date_filters[key] = spec.as_dict()
            column_filters[key] = [spec.to_json()] if spec.active else []
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    column_filters = {
        key: ServicePersonPositionFunc._normalise_values(column_filters[key])
        for key in dict.fromkeys([*request.query_params.keys(), *FILTER_KEYS])
        if key in FILTER_KEYS
    }
    order = normalise_filter_order(filter_order, column_filters)
    filter_order = ",".join(order)
    sort_by = sort_by if sort_by in SORT_KEYS else "position_number"
    direction = "desc" if direction == "desc" else "asc"
    occupancy = occupancy if occupancy in ("all", "occupied", "vacant") else "all"
    data = ServicePersonPositionFunc.get_positions(
        db=db,
        occupancy=occupancy,
        sort_by=sort_by,
        direction=direction,
        column_filters=column_filters,
        date_sort_priority=priorities,
    )

    people = ServicePersonPositionFunc.get_people(db)

    active_query = build_query_string(sort_by, direction, occupancy, column_filters, filter_order, priorities)
    sort_urls = {}
    sort_commands = {}
    for key in SORT_KEYS:
        next_direction = "desc" if sort_by == key and direction == "asc" else "asc"
        sort_urls[key] = "?" + build_query_string(
            key,
            next_direction,
            occupancy,
            column_filters,
            filter_order,
            priorities,
        )
        sort_commands[key] = {
            value: "?" + build_query_string(key, value, occupancy, column_filters, filter_order, priorities)
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
            "table_columns": PERSON_POSITIONS_COLUMNS,
            "date_filters": date_filters,
            "date_priorities": {key: list(value) for key, value in priorities.items()},
            "table_column_filters": {
                "keys": list(FILTER_KEYS),
                "order_parameter": "filter_order",
                "extra": {"occupancy": "all"},
            },
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

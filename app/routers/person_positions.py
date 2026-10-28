from urllib.parse import urlencode
from datetime import date
from app.services.staff_read import table_context
from app.services.person_picker import picker_json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database.db import get_db
from app.services.service_person_positions import FILTER_KEYS, DATE_FILTER_KEYS, SORT_KEYS, TEXT_FILTERS, ServicePersonPositionFunc
from app.table_columns import PERSON_POSITIONS_COLUMNS
from app.utils.date_query import DateFilter, date_priority
from app.templating import templates


router = APIRouter()

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
    for key in DATE_FILTER_KEYS:
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
    try:
        raw_version=request.query_params.get("version_id")
        raw_date=request.query_params.get("as_of")
        structures,versions,chosen,on=table_context(
            db,int(raw_version) if raw_version else None,date.fromisoformat(raw_date) if raw_date else None)
    except ValueError as error: raise HTTPException(400,str(error)) from error
    version_id=chosen.id if chosen else -1
    # Read only fields allowed by this table, not arbitrary model attributes.
    column_filters = {key: field_values.get(key, request.query_params.getlist(key)) for key in FILTER_KEYS}
    try:
        for alias in TEXT_FILTERS:
            values=[str(v).strip() for v in column_filters[alias] if str(v).strip()]
            if len(values)>1 or any(len(v)>250 for v in values):raise ValueError('Містить текст: один запит до 250 символів на колонку.')
            column_filters[alias]=values
        priorities = {key: date_priority(field_values.get(f"{key}_priority", request.query_params.get(f"{key}_priority", "year,month,day")))
                      for key in DATE_FILTER_KEYS}
        date_filters = {}
        for key in DATE_FILTER_KEYS:
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
        date_sort_priority=priorities, version_id=version_id, on=on, mirage_filter=request.query_params.get("mirage","all"),
    )

    people = ServicePersonPositionFunc.get_people(db,on)

    def contextual(query):
        query += "&" + urlencode({"mirage":request.query_params.get("mirage","all")})
        return query + "&" + urlencode({"version_id":version_id,"as_of":on.isoformat()}) if chosen else query

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

    active_query=contextual(active_query)
    sort_urls={key:contextual(value) for key,value in sort_urls.items()}
    sort_commands={key:{direction:contextual(value) for direction,value in commands.items()} for key,commands in sort_commands.items()}

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
            "filter_numbers": {TEXT_FILTERS.get(key,key): index + 1 for index, key in enumerate(order)},
            "sort_commands": sort_commands,
            "mirage_filter":request.query_params.get("mirage","all"),"people_labels":{p["id"]:p["rank"]+" "+p["label"] for p in people},
            "people": people, "people_json":picker_json(people),
            "staff_versions":versions,"staff_structures":structures,"structure_names":{item.id:f"{item.name} ({item.code})" for item in structures},"chosen_version":chosen,"as_of":on,
            "staff_message":request.query_params.get("staff_message", ""),
            "table_columns": PERSON_POSITIONS_COLUMNS,
            "date_filters": date_filters,
            "date_priorities": {key: list(value) for key, value in priorities.items()},
            "table_column_filters": {
                "keys": list(FILTER_KEYS),"column_keys":TEXT_FILTERS,
                "order_parameter": "filter_order",
                "extra": {"occupancy": "all", "mirage":"all"},
            },
        },
    )


# Assignment requests are handled by the shared staff router with signed previews.

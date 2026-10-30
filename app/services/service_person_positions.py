from app.repositories.position_table_repository import (
    PositionTableRepository, HISTORY_MODELS, EMPTY_FILTER_VALUE,
    FILTER_COLUMNS, DATE_FILTER_COLUMNS, SORT_COLUMNS,
)
from app.services.staff_service import today, StaffService
from app.medical_catalog import FITNESS
from app.table_columns import PERSON_POSITIONS_FIELDS

HISTORY_SOURCES = tuple(zip(("name", "person_rank", "passport", "service"),
                           HISTORY_MODELS, ("ПІБ", "звання", "паспорт", "служба")))
TEXT_FILTERS = {key+"__contains":key for key,field in PERSON_POSITIONS_FIELDS.items() if field.data_type=="text"}
FILTER_KEYS = (*FILTER_COLUMNS, *DATE_FILTER_COLUMNS, *TEXT_FILTERS)
DATE_FILTER_KEYS = tuple(DATE_FILTER_COLUMNS)
SORT_KEYS = (*SORT_COLUMNS, *DATE_FILTER_COLUMNS)


def _row(record):
    keys = ("position", "assignment", "person", "name", "person_rank", "rank", "passport", "service")
    row = dict(zip(keys, record[:8]))
    row["full_address"] = record[16] if len(record)>16 else None
    row['medical_exam']=record[17] if len(record)>17 else None
    projected=[field.key for field in PERSON_POSITIONS_FIELDS.values() if field.source=='person' and field.group in ('medical','injuries','awards','tasks','dna')]
    row['medical_values']=dict(zip(projected,record[19:]))
    row["warnings"] = []
    if len(record)>18 and record[18]:row['warnings'].append('Активне ВЛК не визначено: однакові або відсутні дати.')
    for index, (source, _, label) in enumerate(HISTORY_SOURCES):
        total, active = record[8 + index * 2:10 + index * 2]
        if total and total > 1 and active != 1:
            row["warnings"].append(f"{label}: записів {total}, активних {active}; однозначний вибір неможливий.")
    row["values"] = {key: field.display(row) for key, field in PERSON_POSITIONS_FIELDS.items()}
    return row


class ServicePersonPositionFunc:
    _normalise_values = staticmethod(PositionTableRepository._normalise_values)

    @staticmethod
    def get_people(db, on=None):
        from app.services.person_picker import person_options
        return person_options(db, on or today())

    @staticmethod
    def _filter_options(repository, column_filters, occupancy, rows):
        # All inactive facets use the already-fetched rows. Only an active facet
        # needs another SQL query excluding itself: queries scale with filters,
        # never with people, columns, or the number of historic records.
        options = {}
        for key, field in PERSON_POSITIONS_FIELDS.items():
            if not field.filterable:
                continue
            candidates = rows
            if column_filters.get(key) or column_filters.get(key+"__contains"):
                records = repository.records(column_filters, occupancy, exclude_key=key)
                candidates = [_row(record) for record in records]
            if field.data_type == "partial_date":
                values = [field.value(row) for row in candidates if row.get(field.source) is not None]
                from datetime import date
                from app.utils.date_utils import DateComponents
                values=[DateComponents(v.day,v.month,v.year) if type(v) is date else v for v in values if v is not None]
                options[key] = {plural: sorted({getattr(value, part) for value in values if getattr(value, part) is not None})
                                for plural, part in (("days", "day"), ("months", "month"), ("years", "year"))}
            else:
                values = {field.value(row) for row in candidates}
                known = sorted(value for value in values if value is not None and value != "")
                items = [{"value": str(int(value)) if field.data_type == "boolean" else str(value),
                          "label": ("Так" if value else "Ні") if field.data_type == "boolean" else FITNESS.get(value,str(value)) if key=="medical_fitness" else str(value)} for value in known]
                if None in values or "" in values:
                    items.insert(0, {"value": EMPTY_FILTER_VALUE, "label": "Порожньо"})
                options[key] = items
        return options

    @staticmethod
    def get_positions(db, unit_short=None, occupancy="all", sort_by="position_number", direction="asc",
                      column_filters=None, date_sort_priority=None, version_id=None, on=None, mirage_filter="all"):
        direction = "desc" if direction == "desc" else "asc"
        repository = PositionTableRepository(db, version_id, on or today(),mirage_filter)
        column_filters = dict(column_filters or {})
        if unit_short and not column_filters.get("unit_short"):
            column_filters["unit_short"] = unit_short
        rows = [_row(record) for record in repository.records(
            column_filters, occupancy, sort_by=sort_by, direction=direction,
            date_sort_priority=date_sort_priority)]
        from app.repositories.service_history_repository import ServiceHistoryRepository
        mirages={}
        for record,position in ServiceHistoryRepository.mirages(db,position_ids=[r['position'].position_id for r in rows]):
            mirages.setdefault(position.position_id,[]).append(record)
        occupied = sum(row["assignment"] is not None for row in rows)
        return {"rows": rows,"mirages_by_position":mirages,
                "filter_options": ServicePersonPositionFunc._filter_options(repository, column_filters, occupancy, rows),
                "total": len(rows), "occupied": occupied, "vacant": len(rows) - occupied,
                "data_warnings": [{"position_number": row["position"].position_number, "messages": row["warnings"]}
                                  for row in rows if row["warnings"]]}

    @staticmethod
    def assign_person_to_position(position_id, person_id, db, *, on, expected, confirmed=False):
        return StaffService.assign(db,position_id,person_id,on,expected,confirmed)

from sqlalchemy import case, func, or_

from app.models.person import Person
from app.models.person_identity import Passport, PersonName
from app.models.person_military_service import PersonRank, PersonServiceHistory
from app.models.person_positions import PersonPosition
from app.models.reference_book import Position, Rank
from app.table_columns import PERSON_POSITIONS_FIELDS
from app.utils.date_query import DateFilter, date_priority


EMPTY_FILTER_VALUE = "__empty__"
FILTER_COLUMNS = {key: field.expression for key, field in PERSON_POSITIONS_FIELDS.items()
                  if field.filterable and field.data_type != "partial_date"}
DATE_FILTER_COLUMNS = {key: field.date_binding for key, field in PERSON_POSITIONS_FIELDS.items()
                       if field.data_type == "partial_date"}
DATE_FILTER_RECORDS = {key: PERSON_POSITIONS_FIELDS[key].record_id for key in DATE_FILTER_COLUMNS}
SORT_COLUMNS = {key: field.expression for key, field in PERSON_POSITIONS_FIELDS.items()
                if field.data_type != "partial_date"}
HISTORY_SOURCES = (("name", PersonName, "ПІБ"), ("person_rank", PersonRank, "звання"),
                   ("passport", Passport, "паспорт"), ("service", PersonServiceHistory, "служба"))


def history_selection(model):
    """Exactly one total record, otherwise exactly one active record; no recency fallback.

    This grouped subquery contributes at most one row per person, even for
    inconsistent historic data. No stored record or active flag is modified.
    """
    pk = model.__mapper__.primary_key[0]
    active_count = func.sum(case((model.is_active.is_(True), 1), else_=0))
    chosen = case((func.count() == 1, func.min(pk)),
                  (active_count == 1, func.max(case((model.is_active.is_(True), pk), else_=None))),
                  else_=None)
    return (model.__table__.select().with_only_columns(
        model.person_id.label("person_id"), chosen.label("chosen_id"),
        func.count().label("total"), active_count.label("active_count"),
    ).group_by(model.person_id).subquery())


def _row(record):
    keys = ("position", "assignment", "person", "name", "person_rank", "rank", "passport", "service")
    row = dict(zip(keys, record[:8]))
    row["warnings"] = []
    for index, (source, _, label) in enumerate(HISTORY_SOURCES):
        total, active = record[8 + index * 2:10 + index * 2]
        if total and total > 1 and active != 1:
            row["warnings"].append(f"{label}: записів {total}, активних {active}; однозначний вибір неможливий.")
    row["values"] = {key: field.display(row) for key, field in PERSON_POSITIONS_FIELDS.items()}
    return row


class ServicePersonPositionFunc:
    @staticmethod
    def _base_query(db):
        selections = [(model, history_selection(model)) for _, model, _ in HISTORY_SOURCES]
        query = (db.query(Position, PersonPosition, Person, PersonName, PersonRank, Rank, Passport, PersonServiceHistory)
                 .outerjoin(PersonPosition, Position.position_id == PersonPosition.position_id)
                 .outerjoin(Person, PersonPosition.person_id == Person.person_id))
        for model, selection in selections:
            query = (query.outerjoin(selection, selection.c.person_id == Person.person_id)
                     .outerjoin(model, model.__mapper__.primary_key[0] == selection.c.chosen_id)
                     .add_columns(selection.c.total, selection.c.active_count))
        return query.outerjoin(Rank, PersonRank.rank_id == Rank.rank_id)

    @staticmethod
    def get_people(db):
        selection = history_selection(PersonName)
        records = (db.query(Person, PersonName)
                   .outerjoin(selection, selection.c.person_id == Person.person_id)
                   .outerjoin(PersonName, PersonName.person_name_id == selection.c.chosen_id)
                   .order_by(PersonName.surname, PersonName.name, Person.person_id).all())
        return [{"person": person, "name": name} for person, name in records]

    @staticmethod
    def _normalise_values(values):
        if values is None:
            return []
        if isinstance(values, str):
            values = [values]
        return list(dict.fromkeys(value for value in values if value != ""))

    @staticmethod
    def _apply_value_filter(query, column, values, data_type="text"):
        values = ServicePersonPositionFunc._normalise_values(values)
        if not values:
            return query
        regular = [value for value in values if value != EMPTY_FILTER_VALUE]
        if data_type in ("integer", "boolean"):
            converted = []
            for value in regular:
                try:
                    number = int(value)
                    if data_type != "boolean" or number in (0, 1):
                        converted.append(number)
                except (TypeError, ValueError):
                    pass
            regular = converted
        conditions = [column.in_(regular)] if regular else []
        if EMPTY_FILTER_VALUE in values:
            conditions.append(column.is_(None))
            if data_type == "text":
                conditions.append(column == "")
        return query.filter(or_(*conditions)) if conditions else query.filter(False)

    @staticmethod
    def _apply_filters(query, column_filters, occupancy, exclude_key=None):
        for key, column in FILTER_COLUMNS.items():
            if key != exclude_key:
                query = ServicePersonPositionFunc._apply_value_filter(
                    query, column, column_filters.get(key), PERSON_POSITIONS_FIELDS[key].data_type)
        for key, binding in DATE_FILTER_COLUMNS.items():
            if key != exclude_key and column_filters.get(key):
                values = ServicePersonPositionFunc._normalise_values(column_filters[key])
                if len(values) != 1:
                    raise ValueError("Фільтр дати має бути заданий один раз.")
                spec = DateFilter.from_json(values[0])
                if spec.active:
                    query = binding.filter(query.filter(DATE_FILTER_RECORDS[key].is_not(None)), spec)
        if occupancy == "occupied":
            query = query.filter(PersonPosition.person_position_id.is_not(None))
        elif occupancy == "vacant":
            query = query.filter(PersonPosition.person_position_id.is_(None))
        return query

    @staticmethod
    def _filter_options(base_query, column_filters, occupancy, rows):
        # All inactive facets use the already-fetched rows. Only an active facet
        # needs another SQL query excluding itself: queries scale with filters,
        # never with people, columns, or the number of historic records.
        options = {}
        for key, field in PERSON_POSITIONS_FIELDS.items():
            if not field.filterable:
                continue
            candidates = rows
            if column_filters.get(key):
                records = ServicePersonPositionFunc._apply_filters(base_query, column_filters, occupancy, exclude_key=key).all()
                candidates = [_row(record) for record in records]
            if field.data_type == "partial_date":
                values = [field.value(row) for row in candidates if row[field.source] is not None]
                options[key] = {plural: sorted({getattr(value, part) for value in values if getattr(value, part) is not None})
                                for plural, part in (("days", "day"), ("months", "month"), ("years", "year"))}
            else:
                values = {field.value(row) for row in candidates}
                known = sorted(value for value in values if value is not None and value != "")
                items = [{"value": str(int(value)) if field.data_type == "boolean" else str(value),
                          "label": ("Так" if value else "Ні") if field.data_type == "boolean" else str(value)} for value in known]
                if None in values or "" in values:
                    items.insert(0, {"value": EMPTY_FILTER_VALUE, "label": "Порожньо"})
                options[key] = items
        return options

    @staticmethod
    def get_positions(db, unit_short=None, occupancy="all", sort_by="position_number", direction="asc",
                      column_filters=None, date_sort_priority=None):
        direction = "desc" if direction == "desc" else "asc"
        base_query = ServicePersonPositionFunc._base_query(db)
        column_filters = dict(column_filters or {})
        if unit_short and not column_filters.get("unit_short"):
            column_filters["unit_short"] = unit_short
        query = ServicePersonPositionFunc._apply_filters(base_query, column_filters, occupancy)
        if sort_by in DATE_FILTER_COLUMNS:
            priority = date_sort_priority.get(sort_by) if isinstance(date_sort_priority, dict) else date_sort_priority
            orders = DATE_FILTER_COLUMNS[sort_by].order_by(date_priority(priority), direction)
        else:
            column = SORT_COLUMNS.get(sort_by, Position.position_number)
            orders = [column.desc() if direction == "desc" else column.asc()]
        rows = [_row(record) for record in query.order_by(*orders, Position.position_number, Position.position_id).all()]
        occupied = sum(row["assignment"] is not None for row in rows)
        return {"rows": rows,
                "filter_options": ServicePersonPositionFunc._filter_options(base_query, column_filters, occupancy, rows),
                "total": len(rows), "occupied": occupied, "vacant": len(rows) - occupied,
                "data_warnings": [{"position_number": row["position"].position_number, "messages": row["warnings"]}
                                  for row in rows if row["warnings"]]}

    @staticmethod
    def assign_person_to_position(position_id: int, person_id: int | None, db):
        position = db.get(Position, position_id)
        if not position:
            raise ValueError("Штатну позицію не знайдено")

        if person_id is not None:
            person = db.get(Person, person_id)
            if not person:
                raise ValueError("Військовослужбовця не знайдено")

        try:
            target_assignment = (
                db.query(PersonPosition)
                .filter(PersonPosition.position_id == position_id)
                .first()
            )
            if person_id is None:
                if target_assignment:
                    db.delete(target_assignment)
                db.commit()
                return None

            previous_assignment = (
                db.query(PersonPosition)
                .filter(
                    PersonPosition.person_id == person_id,
                    PersonPosition.position_id != position_id,
                )
                .first()
            )
            if previous_assignment:
                db.delete(previous_assignment)
                db.flush()

            if target_assignment:
                target_assignment.person_id = person_id
            else:
                target_assignment = PersonPosition(
                    person_id=person_id,
                    position_id=position_id,
                )
                db.add(target_assignment)

            db.commit()
            db.refresh(target_assignment)
            return target_assignment
        except Exception:
            db.rollback()
            raise

from sqlalchemy import and_, or_

from app.models.person import Person
from app.models.person_identity import PersonName
from app.models.person_military_service import PersonRank
from app.models.person_positions import PersonPosition
from app.models.reference_book import Position, Rank
from app.date_fields import BIRTH_DATE
from app.utils.date_query import DateBinding, DateFilter, date_priority


EMPTY_FILTER_VALUE = "__empty__"
FILTER_COLUMNS = {
    "position_number": Position.position_number,
    "unit_short": Position.unit_short,
    "name_short": Position.name_short,
    "name_nominative": Position.name_nominative,
    "rank": Rank.nominative,
    "surname": PersonName.surname,
    "name": PersonName.name,
    "patronymic": PersonName.patronymic,
}
DATE_FILTER_COLUMNS = {
    "birth_date": DateBinding(BIRTH_DATE, Person.birth_day, Person.birth_month, Person.birth_year),
    "rank_order_date": PersonRank.date_binding("rank_order"),
}
DATE_FILTER_RECORDS = {"birth_date": Person.person_id, "rank_order_date": PersonRank.person_rank_id}


class ServicePersonPositionFunc:

    @staticmethod
    def _base_query(db):
        return (
            db.query(
                Position,
                PersonPosition,
                Person,
                PersonName,
                PersonRank,
                Rank,
            )
            .outerjoin(
                PersonPosition,
                Position.position_id == PersonPosition.position_id,
            )
            .outerjoin(Person, PersonPosition.person_id == Person.person_id)
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
            .outerjoin(Rank, PersonRank.rank_id == Rank.rank_id)
        )

    @staticmethod
    def _normalise_values(values):
        if values is None:
            return []
        if isinstance(values, str):
            values = [values]
        return list(dict.fromkeys(value for value in values if value != ""))

    @staticmethod
    def _apply_value_filter(query, column, values):
        values = ServicePersonPositionFunc._normalise_values(values)
        if not values:
            return query

        include_empty = EMPTY_FILTER_VALUE in values
        regular_values = [value for value in values if value != EMPTY_FILTER_VALUE]
        if column is Position.position_number:
            numbers = []
            for value in regular_values:
                try:
                    numbers.append(int(value))
                except (TypeError, ValueError):
                    pass
            regular_values = numbers
        conditions = []
        if regular_values:
            conditions.append(column.in_(regular_values))
        if include_empty:
            conditions.append(column.is_(None))
            if column is not Position.position_number:
                conditions.append(column == "")
        return query.filter(or_(*conditions)) if conditions else query.filter(False)

    @staticmethod
    def _apply_filters(query, column_filters, occupancy, exclude_key=None):
        for key, column in FILTER_COLUMNS.items():
            if key != exclude_key:
                query = ServicePersonPositionFunc._apply_value_filter(
                    query, column, column_filters.get(key)
                )
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
    def _filter_options(base_query, column_filters, occupancy):
        options = {}
        for key, column in FILTER_COLUMNS.items():
            query = ServicePersonPositionFunc._apply_filters(
                base_query, column_filters, occupancy, exclude_key=key
            )
            records = query.with_entities(column).distinct().order_by(column).all()
            values = {}
            for (value,) in records:
                is_empty = value is None or value == ""
                option_value = EMPTY_FILTER_VALUE if is_empty else str(value)
                values[option_value] = {
                    "value": option_value,
                    "label": "Порожньо" if is_empty else str(value),
                }
            options[key] = list(values.values())
        for key, binding in DATE_FILTER_COLUMNS.items():
            query = ServicePersonPositionFunc._apply_filters(base_query, column_filters, occupancy, exclude_key=key)
            records = query.with_entities(binding.day, binding.month, binding.year).filter(DATE_FILTER_RECORDS[key].is_not(None)).distinct().all()
            options[key] = {part: sorted({record[index] for record in records if record[index] is not None})
                            for index, part in enumerate(("days", "months", "years"))}
        return options

    @staticmethod
    def get_positions(
        db,
        unit_short=None,
        occupancy: str = "all",
        sort_by: str = "position_number",
        direction: str = "asc",
        column_filters: dict[str, list[str]] | None = None,
        date_sort_priority=None,
    ):
        sort_column = FILTER_COLUMNS.get(sort_by, Position.position_number)
        direction = "desc" if direction == "desc" else "asc"
        order = sort_column.desc() if direction == "desc" else sort_column.asc()

        base_query = ServicePersonPositionFunc._base_query(db)
        column_filters = dict(column_filters or {})
        if unit_short and not column_filters.get("unit_short"):
            column_filters["unit_short"] = unit_short
        query = ServicePersonPositionFunc._apply_filters(base_query, column_filters, occupancy)
        priority = date_sort_priority.get(sort_by) if isinstance(date_sort_priority, dict) else date_sort_priority
        orders = DATE_FILTER_COLUMNS[sort_by].order_by(date_priority(priority), direction) if sort_by in DATE_FILTER_COLUMNS else [order]
        records = query.order_by(*orders, Position.position_number, Position.position_id).all()
        rows = [
            {
                "position": position,
                "assignment": assignment,
                "person": person,
                "name": name,
                "person_rank": person_rank,
                "rank": rank,
            }
            for position, assignment, person, name, person_rank, rank in records
        ]
        total = len(rows)
        occupied = sum(1 for row in rows if row["assignment"] is not None)

        return {
            "rows": rows,
            "filter_options": ServicePersonPositionFunc._filter_options(
                base_query, column_filters, occupancy
            ),
            "total": total,
            "occupied": occupied,
            "vacant": total - occupied,
        }

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

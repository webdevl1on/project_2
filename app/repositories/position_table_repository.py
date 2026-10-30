"""Read queries for the staff table; whitelisted field metadata only."""
from sqlalchemy import or_, and_

from app.models.person import Person
from app.models.person_identity import Passport, PersonName
from app.models.person_military_service import PersonRank, PersonServiceHistory
from app.models.staff import PersonAssignment as PersonPosition, StaffVersion
from app.repositories.staff_repository import active
from app.repositories.person_repository import history_selection
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
HISTORY_MODELS = (PersonName, PersonRank, Passport, PersonServiceHistory)


class PositionTableRepository:
    def __init__(self, db, version_id, on, mirage_filter="all"):
        from app.models import PersonPositionMirage
        from sqlalchemy import exists
        self._query = self._base_query(db, version_id, on)
        has=exists().where(PersonPositionMirage.staff_position_id==Position.position_id,PersonPositionMirage.status=='waiting')
        if mirage_filter=='with':self._query=self._query.filter(has)
        elif mirage_filter=='without':self._query=self._query.filter(~has)

    @staticmethod
    def _base_query(db, version_id=None, on=None):
        selections = [(model, history_selection(model)) for model in HISTORY_MODELS]
        query = (db.query(Position, PersonPosition, Person, PersonName, PersonRank, Rank, Passport, PersonServiceHistory)
                 .join(StaffVersion, StaffVersion.id == Position.staff_version_id)
                 .filter(StaffVersion.id == version_id if version_id is not None else active(StaffVersion,"valid_from","valid_to",on))
                 .outerjoin(PersonPosition, and_(Position.position_id == PersonPosition.position_id, active(PersonPosition,"assigned_from","assigned_to",on)))
                 .outerjoin(Person, PersonPosition.person_id == Person.person_id))
        for model, selection in selections:
            query = (query.outerjoin(selection, selection.c.person_id == Person.person_id)
                     .outerjoin(model, model.__mapper__.primary_key[0] == selection.c.chosen_id)
                     .add_columns(selection.c.total, selection.c.active_count))
        from app.repositories.medical_repository import active_exam_selection
        from app.models import MedicalExam
        chosen=active_exam_selection()
        return (query.outerjoin(Rank, PersonRank.rank_id == Rank.rank_id).add_columns(PERSON_POSITIONS_FIELDS["full_address"].expression)
                .outerjoin(chosen,chosen.c.person_id==Person.person_id).outerjoin(MedicalExam,MedicalExam.id==chosen.c.chosen_id)
                .add_columns(MedicalExam,chosen.c.ambiguous,*[field.expression for field in PERSON_POSITIONS_FIELDS.values() if field.source=='person' and field.group in ('medical','injuries','awards','tasks','dna')]))

    @staticmethod
    def _normalise_values(values):
        if values is None:
            return []
        if isinstance(values, str):
            values = [values]
        return list(dict.fromkeys(value for value in values if value != ""))

    @staticmethod
    def _apply_value_filter(query, column, values, data_type="text"):
        values = PositionTableRepository._normalise_values(values)
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
        from app.utils.text_search import contains_clause
        for key,field in PERSON_POSITIONS_FIELDS.items():
            alias=key+'__contains'
            if field.data_type=='text' and key!=exclude_key and column_filters.get(alias):
                values=PositionTableRepository._normalise_values(column_filters[alias])
                if len(values)!=1:raise ValueError('Містить текст: один запит на колонку.')
                query=query.filter(contains_clause(field.expression,values[0]))
        for key, column in FILTER_COLUMNS.items():
            if key != exclude_key:
                query = PositionTableRepository._apply_value_filter(
                    query, column, column_filters.get(key), PERSON_POSITIONS_FIELDS[key].data_type)
        for key, binding in DATE_FILTER_COLUMNS.items():
            if key != exclude_key and column_filters.get(key):
                values = PositionTableRepository._normalise_values(column_filters[key])
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

    def records(self, column_filters, occupancy, *, exclude_key=None, sort_by=None,
                direction="asc", date_sort_priority=None):
        query = self._apply_filters(self._query, column_filters, occupancy, exclude_key)
        if sort_by is not None:
            if sort_by in DATE_FILTER_COLUMNS:
                priority = date_sort_priority.get(sort_by) if isinstance(date_sort_priority, dict) else date_sort_priority
                orders = DATE_FILTER_COLUMNS[sort_by].order_by(date_priority(priority), direction)
            else:
                column = SORT_COLUMNS.get(sort_by, Position.position_number)
                orders = [column.desc() if direction == "desc" else column.asc()]
            query = query.order_by(*orders, Position.position_number, Position.position_id)
        return query.all()

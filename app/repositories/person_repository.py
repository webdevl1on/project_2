from app.models.person import Person
from app.models.person_identity import PersonName
from app.models.person_military_service import PersonRank
from app.models.reference_book import Rank, Position
from app.models.staff import PersonAssignment
from app.repositories.staff_repository import active
from sqlalchemy import and_, case, func
from app.date_fields import BIRTH_DATE
from app.utils.date_query import DateBinding


class PersonRepository:
    """Person data access. The caller owns validation and transactions."""

    @staticmethod
    def get_by_id(db, person_id):
        return db.query(Person).filter(Person.person_id == person_id).first()

    @staticmethod
    def get_by_tax_number(db, tax_number):
        return db.query(Person).filter(Person.tax_number == tax_number).first()

    @staticmethod
    def add_person(db, person_data):
        person = Person(**person_data)
        db.add(person)
        db.flush()
        return person

    @staticmethod
    def add_name(db, person_id, name_data):
        name = PersonName(
            person_id = person_id,
            **name_data
        )
        db.add(name)
        return name

    @staticmethod
    def get_name(db, key):
        return db.get(PersonName, key)

    @staticmethod
    def current_name(db, person_id, *, exclude=None):
        query = db.query(PersonName).filter_by(person_id=person_id, is_active=True)
        if exclude is not None:
            query = query.filter(PersonName.person_name_id != exclude)
        return query.first()

    @staticmethod
    def name_history(db, person_id):
        return db.query(PersonName).filter_by(person_id=person_id).order_by(PersonName.created_at.desc()).all()

    @staticmethod
    def get_person_rank(db, key):
        return db.get(PersonRank, key)

    @staticmethod
    def current_rank(db, person_id, *, exclude=None):
        query = db.query(PersonRank).filter_by(person_id=person_id, is_active=True)
        if exclude is not None:
            query = query.filter(PersonRank.person_rank_id != exclude)
        return query.first()

    @staticmethod
    def person_rank_by_rank(db, person_id, rank_id):
        return db.query(PersonRank).filter_by(person_id=person_id, rank_id=rank_id).first()

    @staticmethod
    def get_rank(db, rank_id):
        return db.get(Rank, rank_id)

    @staticmethod
    def ranks(db):
        return db.query(Rank).order_by(Rank.rank_id).all()

    @staticmethod
    def add_rank(db, person_id, data):
        record = PersonRank(person_id=person_id, **data)
        db.add(record)
        return record

    @staticmethod
    def delete(db, record):
        db.delete(record)

    @staticmethod
    def list_people(db, sort_by="surname", direction="asc"):
        columns = {"id": Person.person_id, "surname": PersonName.surname,
                   "name": PersonName.name, "birth_year": Person.birth_year,
                   "tax_number": Person.tax_number, "rank": Rank.nominative}
        column = columns.get(sort_by, PersonName.surname)
        orders = (DateBinding(BIRTH_DATE, Person.birth_day, Person.birth_month, Person.birth_year)
                  .order_by(direction=direction)) if sort_by == "birth_year" else [
                      column.desc() if direction == "desc" else column.asc()]
        return (db.query(Person, PersonName, PersonRank)
                .outerjoin(PersonName, and_(PersonName.person_id == Person.person_id, PersonName.is_active.is_(True)))
                .outerjoin(PersonRank, and_(PersonRank.person_id == Person.person_id, PersonRank.is_active.is_(True)))
                .outerjoin(Rank, PersonRank.rank_id == Rank.rank_id)
                .order_by(*orders, Person.person_id).all())

    @staticmethod
    def picker_rows(db, on):
        names=history_selection(PersonName); ranks=history_selection(PersonRank)
        return (db.query(Person,PersonName,Rank,PersonAssignment,Position)
               .outerjoin(names,names.c.person_id==Person.person_id)
               .outerjoin(PersonName,PersonName.person_name_id==names.c.chosen_id)
               .outerjoin(ranks,ranks.c.person_id==Person.person_id)
               .outerjoin(PersonRank,PersonRank.person_rank_id==ranks.c.chosen_id)
               .outerjoin(Rank,Rank.rank_id==PersonRank.rank_id)
               .outerjoin(PersonAssignment,and_(PersonAssignment.person_id==Person.person_id,
                           active(PersonAssignment,"assigned_from","assigned_to",on)))
               .outerjoin(Position,Position.position_id==PersonAssignment.staff_position_id)).all()


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

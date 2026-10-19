"""Real SQLite round-trips; all files and identities are isolated test data."""

from datetime import date
from itertools import product

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, Date, DateTime, Integer, event, func, inspect, select
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.date_fields import DATE_FIELDS
from app.models import Person, PersonName, PersonRank, PersonServiceHistory, Passport, Rank, PersonEvent
from app.models.reference_data.ranks import ReferenceRanks
from app.services.service_common_person_func import CommonPersonFunc
from app.services.service_person_rank import ServicePersonRankFunc
from app.utils.date_query import DateFilter
from app.utils.date_utils import date_values_from_input, format_partial_date


FIELDS = [(Passport, "passport_issued"), (Passport, "passport_expire"),
          (PersonRank, "rank_order"), (PersonServiceHistory, "position"), (PersonServiceHistory, "order")]


@pytest.fixture
def fresh(tmp_path):
    path = tmp_path / "domain_dates.sqlite3"
    engine = create_engine(f"sqlite:///{path}")

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add_all(Rank(**row) for row in ReferenceRanks.RANKS)
        person = Person()
        db.add(person); db.commit()
        yield db, person
    engine.dispose()


def make_record(cls, prefix, parts, db, person):
    kwargs = {f"{prefix}_{part}": value for part, value in zip(("day", "month", "year"), parts)}
    if cls is PersonRank:
        kwargs["rank_id"] = db.scalar(select(Rank.rank_id))
    row = cls(person_id=person.person_id, **kwargs)
    db.add(row)
    return row


@pytest.mark.parametrize("cls,prefix", FIELDS)
@pytest.mark.parametrize("mask", product((False, True), repeat=3))
def test_all_partial_combinations_roundtrip_and_filter(fresh, cls, prefix, mask):
    db, person = fresh
    parts = tuple(value if known else None for value, known in zip((29, 2, 2000), mask))
    row = make_record(cls, prefix, parts, db, person)
    db.commit(); db.refresh(row)
    assert tuple(getattr(row, f"{prefix}_{part}") for part in ("day", "month", "year")) == parts
    expected_date = date(2000, 2, 29) if all(mask) else None
    assert getattr(row, f"{prefix}_date") == expected_date
    assert db.scalar(select(cls.__table__.c[f"{prefix}_date"])) == expected_date
    expected_text = ".".join(str(value).zfill(width) if value is not None else "_" for value, width in zip(parts, (2, 2, 4)))
    assert format_partial_date(*parts) == expected_text
    spec = DateFilter.from_json({"years": [2000], "months": [2], "days": [29]})
    assert cls.date_binding(prefix).filter(db.query(cls), spec).one() is row


@pytest.mark.parametrize("cls,prefix", FIELDS)
def test_legacy_exact_projection_clear_and_invalid_values(fresh, cls, prefix):
    db, person = fresh
    row = make_record(cls, prefix, (None, 2, 2000), db, person)
    setattr(row, f"{prefix}_date", date(2000, 2, 29))
    db.commit(); db.refresh(row)
    assert row.date_components(prefix).as_date() == date(2000, 2, 29)
    setattr(row, f"{prefix}_date", None)
    db.commit(); db.refresh(row)
    assert tuple(getattr(row, f"{prefix}_{part}") for part in ("day", "month", "year")) == (None, None, None)
    setattr(row, f"{prefix}_day", 31); setattr(row, f"{prefix}_month", 2)
    with pytest.raises(ValueError):
        db.commit()
    db.rollback(); db.refresh(row)
    assert row.date_components(prefix).as_dict(prefix) == {f"{prefix}_{part}": None for part in ("day", "month", "year")}


@pytest.mark.parametrize("cls,prefix", FIELDS)
@pytest.mark.parametrize("direction", ["asc", "desc"])
def test_shared_sorting_keeps_exact_then_partial_then_unknown(fresh, cls, prefix, direction):
    db, person = fresh
    known1 = make_record(cls, prefix, (15, 3, 1993), db, person)
    known2 = make_record(cls, prefix, (15, 4, 1993), db, person)
    partial = make_record(cls, prefix, (None, 1, 1970), db, person)
    unknown = make_record(cls, prefix, (None, None, None), db, person)
    db.commit()
    actual = db.scalars(select(cls).order_by(*cls.date_binding(prefix).order_by(direction=direction))).all()
    assert actual == ([known1, known2] if direction == "asc" else [known2, known1]) + [partial, unknown]


def test_schema_has_fifteen_components_and_preserves_event_and_system_types(fresh):
    db, _ = fresh
    inspector = inspect(db.get_bind())
    for cls, prefix in FIELDS:
        columns = {c["name"]: c for c in inspector.get_columns(cls.__tablename__)}
        for part in ("day", "month", "year"):
            assert columns[f"{prefix}_{part}"]["nullable"]
            assert isinstance(columns[f"{prefix}_{part}"]["type"], Integer)
        assert isinstance(cls.__table__.c[f"{prefix}_date"].type, Date)
    for name in ("date_start", "date_end", "order_date"):
        assert isinstance(PersonEvent.__table__.c[name].type, Date)
    for cls in (PersonName, Passport, PersonRank, PersonServiceHistory):
        assert isinstance(cls.__table__.c.created_at.type, DateTime)
        assert isinstance(cls.__table__.c.updated_at.type, DateTime)
        assert cls.__table__.c.updated_at.onupdate is not None
    assert not DATE_FIELDS["event.date_start"].allow_partial
    assert not DATE_FIELDS["history.created_at"].allow_partial


def test_rank_service_refines_in_place_and_accepts_legacy_input(fresh):
    db, person = fresh
    rank_id = db.scalar(select(Rank.rank_id))
    row = ServicePersonRankFunc.add_rank(person.person_id, {"rank_id": rank_id, "rank_order_year": "2000"}, db)
    identity, created = row.person_rank_id, row.created_at
    assert (row.rank_order_day, row.rank_order_month, row.rank_order_year) == (None, None, 2000)
    row = ServicePersonRankFunc.update_person_rank(identity, {"rank_id": rank_id, "rank_order_month": "02"}, db)
    assert row.rank_order_year == 2000 and row.rank_order_day is None
    row = ServicePersonRankFunc.update_person_rank(identity, {"rank_id": rank_id, "rank_order_day": "29"}, db)
    assert row.rank_order_date == date(2000, 2, 29) and row.created_at == created
    assert db.scalar(select(func.count()).select_from(PersonRank)) == 1
    row = ServicePersonRankFunc.update_person_rank(identity, {"rank_id": rank_id, "rank_order_date": "15.03.1995"}, db)
    assert row.date_components("rank_order").as_date() == date(1995, 3, 15)
    with pytest.raises(ValueError):
        ServicePersonRankFunc.update_person_rank(identity, {"rank_id": rank_id, "rank_order_year": 1993, "rank_order_date": "15.03.1995"}, db)
    assert row.rank_order_year == 1995


def test_passport_factory_and_date_input_preserve_unknown_components(fresh):
    db, person = fresh
    passport = CommonPersonFunc.add_pasport(person.person_id, passport_series=None, passport_number=None, passport_issued_by=None,
                                         passport_issued_month="03", passport_issued_year="1995")
    db.add(passport); db.commit(); db.refresh(passport)
    assert (passport.passport_issued_day, passport.passport_issued_month, passport.passport_issued_year) == (None, 3, 1995)
    assert passport.passport_issued_date is None
    assert passport.passport_expire_date is None
    updated = date_values_from_input(DATE_FIELDS["passport.passport_issued_date"], "passport_issued", {"passport_issued_day": "15"}, current=passport)
    assert updated == {"passport_issued_day": 15, "passport_issued_month": 3, "passport_issued_year": 1995}


def test_rank_forms_partial_add_update_legacy_and_invalid_dates(fresh):
    from app.database.db import get_db
    from app.main import app
    db, person = fresh
    rank_id = db.scalar(select(Rank.rank_id))
    def isolated(): yield db
    app.dependency_overrides[get_db] = isolated
    try:
        with TestClient(app) as client:
            payload = {"rank_id": rank_id, "rank_order_day": "", "rank_order_month": "3", "rank_order_year": "1995", "created_at": "1900-01-01"}
            response = client.post(f"/person_ranks/add_rank/{person.person_id}", data=payload, follow_redirects=False)
            assert response.status_code == 303
            row = db.scalar(select(PersonRank))
            assert row.date_components("rank_order").as_dict("rank_order") == {"rank_order_day": None, "rank_order_month": 3, "rank_order_year": 1995}
            created = row.created_at
            response = client.get(f"/person_full_info/{person.person_id}")
            assert response.status_code == 200 and "_.03.1995" in response.text
            assert 'name="rank_order_day"' in response.text and 'name="created_at"' not in response.text
            payload["rank_order_day"] = "15"
            response = client.post(f"/person_ranks/{row.person_rank_id}/update", data=payload, follow_redirects=False)
            assert response.status_code == 303
            db.refresh(row); assert row.rank_order_date == date(1995, 3, 15) and row.created_at == created
            payload.update(rank_order_day="31", rank_order_month="2")
            assert client.post(f"/person_ranks/{row.person_rank_id}/update", data=payload).status_code == 400
            db.refresh(row); assert row.rank_order_date == date(1995, 3, 15)
            assert client.post(f"/person_ranks/{row.person_rank_id}/update", data={"rank_id": rank_id, "rank_order_date": "29.02.2000"}, follow_redirects=False).status_code == 303
            db.refresh(row); assert row.rank_order_date == date(2000, 2, 29)
    finally:
        app.dependency_overrides.clear()

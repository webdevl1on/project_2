from datetime import date, datetime, UTC
from calendar import monthrange
from itertools import permutations, product
import json

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, Date, DateTime, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.date_fields import BIRTH_DATE, DATE_FIELDS, DateField, EVENT_START
from app.models import Person, PersonName, PersonRank, Passport, PersonServiceHistory
from app.services.service_person_positions import ServicePersonPositionFunc
from app.utils.date_query import DateBinding, DateFilter, date_sort_key, possible_match
from app.utils.date_utils import format_partial_date, format_system_timestamp, validate_field_date
from app.validators.event_validatotor import EventValidator
from tests.test_person_positions import make_position


@pytest.fixture
def memory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        yield db
    engine.dispose()


@pytest.mark.parametrize("parts,expected", [
    ((15, 3, 1995), "15.03.1995"), ((None, 3, 1995), "_.03.1995"),
    ((15, None, 1995), "15._.1995"), ((15, 3, None), "15.03._"),
    ((None, None, 1995), "_._.1995"), ((None, None, None), "_._._"),
])
def test_display(parts, expected):
    assert format_partial_date(*parts) == expected


@pytest.mark.parametrize("parts,valid", [
    ((31, 2, None), False), ((29, 2, None), True), ((29, 2, 2023), False),
    ((29, 2, 2000), True), ((29, 2, 1900), False), ((None, None, 1995), True),
    ((31, 4, None), False), ((0, None, None), False), ((None, 13, None), False),
])
def test_calendar_validation(parts, valid):
    if valid:
        validate_field_date(BIRTH_DATE, *parts)
    else:
        with pytest.raises(ValueError):
            validate_field_date(BIRTH_DATE, *parts)


def test_exact_and_system_policies():
    with pytest.raises(ValueError):
        validate_field_date(EVENT_START, None, 3, 1995)
    with pytest.raises(ValueError):
        validate_field_date(EVENT_START)
    assert validate_field_date(DateField("optional", "")).day is None
    assert validate_field_date(DateField("future", ""), 1, 1, 9999).year == 9999
    with pytest.raises(ValueError):
        validate_field_date(BIRTH_DATE, 1, 1, date.today().year + 1)
    with pytest.raises(ValueError):
        DateField("timestamp", "", system=True, allow_partial=True)
    with pytest.raises(ValueError):
        DateField("bad_range", "", min_year=0)
    assert validate_field_date(BIRTH_DATE, None, None, 1995).as_dict("order") == {
        "order_day": None, "order_month": None, "order_year": 1995,
    }
    with pytest.raises(ValueError):
        validate_field_date(DATE_FIELDS["history.created_at"], 1, 1, 2000)


@pytest.mark.parametrize("value", ["15._.1995", "_.03.1995", "29.02.2023", "_._._", "1995-03-15"])
def test_event_rejects_incomplete_or_invalid(value):
    with pytest.raises(ValueError):
        EventValidator.validate_event_date(value)


def test_event_full_and_optional_dates():
    assert EventValidator.validate_event_date("29.02.2000", required=True) == date(2000, 2, 29)
    assert EventValidator.validate_event_date(None) is None
    with pytest.raises(ValueError):
        EventValidator.validate_event_date(None, required=True)
    from types import SimpleNamespace
    from app.services.service_for_person_event import PersonEventService
    with pytest.raises(ValueError):
        PersonEventService.prepare_new_person_event(SimpleNamespace(event_type_id=1))


@pytest.mark.parametrize("parts,expected", [
    ((15, 3, 1993), True), ((None, 3, 1993), True), ((15, None, 1993), True),
    ((None, None, 1993), True), ((15, 3, None), True), ((None, None, None), True),
    ((25, 3, 1993), False), ((15, 4, 1993), False),
])
def test_possible_range_examples(parts, expected):
    spec = DateFilter.from_json({"mode": "range", "start": "1993-03-10", "end": "1993-03-20"})
    assert possible_match(*parts, spec, BIRTH_DATE) is expected


@pytest.mark.parametrize("spec,parts,expected", [
    ({"years": [2023]}, (29, 2, None), False),
    ({"years": [2024]}, (29, 2, None), True),
    ({"years": [2023], "months": [2], "days": [29]}, (None, None, None), False),
    ({"years": [2023, 2024], "months": [2], "days": [29]}, (None, None, None), True),
    ({"months": [3, 4], "days": [5, 15]}, (15, None, 1995), True),
    ({"months": [3, 4], "days": [5, 15]}, (25, None, 1995), False),
    ({"mode": "range", "start": "2023-03-01"}, (29, 2, 2024), True),
    ({"mode": "range", "end": "2023-03-01"}, (29, 2, 2024), False),
    ({"incomplete_only": True}, (15, 3, 1995), False),
    ({"incomplete_only": True, "months": [3]}, (None, None, None), True),
])
def test_possible_components_open_range_and_incomplete(spec, parts, expected):
    assert possible_match(*parts, DateFilter.from_json(spec), BIRTH_DATE) is expected


def test_possible_match_against_exhaustive_calendar():
    # Independent oracle enumerates actual dates, not substituted placeholders.
    dates = [date(y, m, d) for y, m in product((2023, 2024), (2, 3)) for d in range(1, monthrange(y, m)[1] + 1)]
    for parts in product((None, 15, 29), (None, 2, 3), (None, 2023, 2024)):
        spec = DateFilter.from_json({"years": [2023, 2024], "months": [2, 3], "days": [15, 29]})
        expected = any((parts[0] is None or d.day == parts[0]) and (parts[1] is None or d.month == parts[1])
                       and (parts[2] is None or d.year == parts[2]) and d.day in (15, 29) for d in dates)
        assert possible_match(*parts, spec, BIRTH_DATE) is expected


@pytest.mark.parametrize("raw", ['no JSON', '[]', '{"years":[true]}', '{"months":[13]}', '{"days":[0]}',
                                    '{"start":"2023-02-29"}', '{"start":"2024-01-02","end":"2024-01-01"}',
                                    '{"incomplete_only":"false"}'])
def test_bad_filters(raw):
    with pytest.raises(ValueError):
        DateFilter.from_json(raw)


@pytest.mark.parametrize("priority,direction", product(permutations(("year", "month", "day")), ("asc", "desc")))
def test_all_sort_priorities_in_sql(memory, priority, direction):
    parts = [(15, 3, 1995), (5, 4, 1993), (1, 1, 2000), (None, 2, 1994),
             (20, None, 1993), (3, 4, None), (None, None, 1995), (None, None, None)]
    people = [Person(birth_day=d, birth_month=m, birth_year=y) for d, m, y in parts]
    memory.add_all(people); memory.commit()
    binding = DateBinding(BIRTH_DATE, Person.birth_day, Person.birth_month, Person.birth_year)
    actual = memory.scalars(select(Person).order_by(*binding.order_by(priority, direction), Person.person_id)).all()
    expected = sorted(people, key=lambda p: date_sort_key(p.birth_day, p.birth_month, p.birth_year, priority, direction))
    assert [p.person_id for p in actual] == [p.person_id for p in expected]
    known = {"year": [people[1], people[0], people[2]], "month": [people[2], people[0], people[1]],
             "day": [people[2], people[1], people[0]]}[priority[0]]
    if direction == "desc": known = list(reversed(known))
    assert [p.person_id for p in actual[:3]] == [p.person_id for p in known]
    assert all(all(getattr(p, f"birth_{part}") is not None for part in ("day", "month", "year")) for p in actual[:3])
    assert actual[-1].birth_day is actual[-1].birth_month is actual[-1].birth_year is None


def test_sql_filters_cascade_and_exact_date_adapter(memory):
    from app.models import PersonPosition
    positions = [make_position(10, "Перший", "Посада", "Посада"), make_position(20, "Другий", "Посада", "Посада"), make_position(30, "Перший", "Посада", "Посада")]
    people = [Person(birth_day=15, birth_month=3, birth_year=1993), Person(birth_day=15, birth_month=None, birth_year=1993)]
    memory.add_all([*positions, *people]); memory.flush()
    memory.add_all(PersonPosition(person_id=p.person_id, position_id=pos.position_id) for p, pos in zip(people, positions)); memory.commit()
    assert ServicePersonPositionFunc.get_positions(memory, column_filters={"birth_date": ["{}"]})["total"] == 3
    spec = DateFilter.from_json({"mode": "range", "start": "1993-03-10", "end": "1993-03-20"})
    data = ServicePersonPositionFunc.get_positions(memory, column_filters={"birth_date": [spec.to_json()]})
    assert data["total"] == 2 and data["vacant"] == 0
    assert {o["value"] for o in data["filter_options"]["unit_short"]} == {"Перший", "Другий"}
    data = ServicePersonPositionFunc.get_positions(memory, column_filters={"birth_date": [spec.to_json()], "unit_short": ["Перший"]})
    assert data["total"] == 1
    assert data["filter_options"]["birth_date"]["years"] == [1993]
    # Component binding preserves known passport parts; event fields keep SQL Date.
    passport = Passport(person_id=people[0].person_id, passport_issued_date=date(1993, 3, 15))
    memory.add(passport); memory.commit()
    binding = Passport.date_binding("passport_issued")
    assert binding.filter(memory.query(Passport), spec).one() == passport
    from app.models import PersonEvent, EventType
    event_type = EventType(event_type="DATE_TEST", event_name="Дата")
    memory.add(event_type); memory.flush()
    event = PersonEvent(person_id=people[0].person_id, event_type_id=event_type.event_type_id, date_start=date(1993, 3, 15))
    memory.add(event); memory.commit()
    exact = DateBinding.exact(EVENT_START, PersonEvent.date_start)
    assert exact.filter(memory.query(PersonEvent), spec).one() == event


def test_system_time_storage_and_form_protection(memory):
    from app.main import app
    from app.database.db import get_db
    for cls in (PersonName, PersonRank, Passport, PersonServiceHistory):
        assert isinstance(cls.__table__.c.created_at.type, DateTime)
        assert isinstance(cls.__table__.c.updated_at.type, DateTime)
        assert cls.__table__.c.updated_at.onupdate is not None
    person = Person(); memory.add(person); memory.flush()
    name = PersonName(person_id=person.person_id, surname="Тестенко", name="Тестослав")
    memory.add(name); memory.commit(); memory.refresh(name)
    created, updated = name.created_at, name.updated_at
    assert created.tzinfo is None  # Existing SQLite storage policy is unchanged.
    assert format_system_timestamp(created).endswith(" UTC")
    assert format_system_timestamp(datetime(2000, 1, 1, 12, 30, tzinfo=UTC)) == "01.01.2000 12:30:00.000000 UTC"
    def isolated(): yield memory
    app.dependency_overrides[get_db] = isolated
    try:
        with TestClient(app) as client:
            response = client.post(f"/persons/{person.person_id}/edit", data={
                "surname": "Зміненко", "name": "Тестослав", "created_at": "1900-01-01", "updated_at": "1900-01-01",
            }, follow_redirects=False)
            assert response.status_code == 303
            memory.refresh(name)
            assert name.created_at == created and name.updated_at >= updated
            detail = client.get(f"/person_detail/{person.person_id}")
            assert "UTC" in detail.text and "date_from" not in detail.text
            form = client.get(f"/persons/{person.person_id}/edit")
            assert 'name="created_at"' not in form.text and 'name="updated_at"' not in form.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("direction,indices", [("asc", [0, 1, 2, 3]), ("desc", [1, 0, 2, 3])])
def test_legacy_people_sort_url_uses_shared_date_order(memory, direction, indices):
    from starlette.requests import Request
    from app.routers.persons import get_persons_page
    people = [Person(birth_day=15, birth_month=3, birth_year=1993),
              Person(birth_day=15, birth_month=4, birth_year=1993),
              Person(birth_day=None, birth_month=1, birth_year=1970), Person()]
    memory.add_all(people); memory.commit()
    request = Request({"type": "http", "method": "GET", "path": "/persons", "query_string": b"", "headers": []})
    response = get_persons_page(request, sort_by="birth_year", direction=direction, db=memory)
    assert [item["person"].person_id for item in response.context["persons"]] == [people[index].person_id for index in indices]

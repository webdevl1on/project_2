"""Catalogue integration checks with synthetic data and isolated SQLite."""
from datetime import date, datetime
from urllib.parse import urlencode, parse_qs

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.database.db import get_db
from app.main import app
from app.models import Person, PersonName, PersonRank, PersonServiceHistory, Passport, PersonPosition, Position, Rank
from app.services.service_person_positions import ServicePersonPositionFunc as Service
from app.table_columns import PERSON_POSITIONS_COLUMNS, PERSON_POSITIONS_FIELDS, table_configuration
from app.table_fields import FIELDS
from app.utils.date_query import DateFilter
from tests.test_person_positions import make_position, make_rank


@pytest.fixture
def catalog_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def populate(db, number=1):
    person = Person(tax_number=f"{number:010}", birth_day=15, birth_year=1990)
    position = make_position(number, "Підрозділ", "Водій", "Водій роти")
    rank = make_rank(); rank.code = f"rank-{number}"
    db.add_all([person, position, rank]); db.flush()
    records = {
        "name": PersonName(person_id=person.person_id, surname="Тестенко", name="Іван", patronymic="Тестович",
                           surname_latin="Testenko", name_latin="Ivan", patronymic_latin=None, is_active=False),
        "person_rank": PersonRank(person_id=person.person_id, rank_id=rank.rank_id, rank_order_number="0012",
                                  rank_order_month=3, rank_order_year=2020, is_active=False),
        "passport": Passport(person_id=person.person_id, passport_type="ID", passport_number="000123",
                             passport_issued_by="Тестовий орган", passport_issued_year=2015, is_active=False),
        "service": PersonServiceHistory(person_id=person.person_id, service_type="Контракт", military_unit="Тестова частина",
                                        position="Водій", order_number="0007", position_year=2019, order_month=6, is_active=False),
    }
    db.add_all([*records.values(), PersonPosition(person_id=person.person_id, position_id=position.position_id)])
    db.commit()
    return person, position, rank, records


def test_catalogue_covers_all_displayable_mapped_attributes():
    # A new model attribute must be deliberately represented or excluded.
    # FK/PK link entities, date projections duplicate the canonical components.
    exclusions = {Person: {"person_id"}, PersonName: {"person_name_id", "person_id"},
                  PersonRank: {"person_rank_id", "person_id", "rank_id", "rank_order_date"},
                  Passport: {"passport_id", "person_id", "passport_issued_date", "passport_expire_date"},
                  PersonServiceHistory: {"person_service_history_id", "person_id", "position_date", "order_date"},
                  Position: {"position_id", "staff_version_id", "created_at", "updated_at", "revision"}, Rank: {"rank_id"}}
    for model, excluded in exclusions.items():
        covered = {attr for field in FIELDS.values() if field.metadata()["source"]["model"] == model.__name__
                   for attr in field.metadata()["source"]["attributes"]}
        # Mapper attributes use private names for the exact-date projections.
        actual = {column.name for column in inspect(model).columns} - excluded
        assert actual <= covered, (model.__name__, actual - covered)
    assert all(field.group not in ("events", "event_types", "event_subtypes") for field in FIELDS.values())
    assert len(FIELDS) == 54
    assert set(PERSON_POSITIONS_FIELDS) == set(FIELDS)


def test_table_configuration_reuses_fields_without_sharing_mutable_metadata():
    first = table_configuration("first", [("person", ["surname", "birth_date"])],
                                overrides={"surname": {"label": "Власна назва", "default_visible": False}})
    second = table_configuration("second", [("person", ["surname"])])
    assert first["groups"][0]["columns"][0]["label"] == "Власна назва"
    assert second["groups"][0]["columns"][0]["label"] == FIELDS["surname"].label
    assert first["groups"][0]["columns"][1]["date"]["allow_partial"] is True
    with pytest.raises(ValueError):
        table_configuration("duplicate", [("person", ["surname", "surname"])])
    with pytest.raises(KeyError):
        table_configuration("unknown", [("person", ["arbitrary_client_attribute"])])


def test_single_inactive_records_are_displayed_and_vacancies_are_empty(catalog_db):
    person, position, rank, records = populate(catalog_db)
    catalog_db.add(make_position(2, "Інший", "Медик", "Медик")); catalog_db.commit()
    result = Service.get_positions(catalog_db)
    row, vacant = result["rows"]
    assert row["values"]["full_name"] == "Тестенко Іван Тестович"
    assert row["values"]["tax_number"] == "0000000001"
    assert row["values"]["passport_number"] == "000123"
    assert row["values"]["rank_order_number"] == "0012"
    assert row["values"]["birth_date"] == "15._.1990"
    assert row["values"]["rank_order_date"] == "_.03.2020"
    assert row["values"]["passport_issued_date"] == "_._.2015"
    assert row["values"]["service_order_date"] == "_.06._"
    assert row["values"]["passport_is_active"] == "Ні"
    assert row["values"]["name_created_at"].endswith(" UTC")
    assert row["values"]["passport_series"] == "-"
    assert not result["data_warnings"]
    for key, field in FIELDS.items():
        if field.source != "position":
            assert vacant["values"][key] == "-", key


@pytest.mark.parametrize("source,model", [("name", PersonName), ("person_rank", PersonRank), ("passport", Passport), ("service", PersonServiceHistory)])
@pytest.mark.parametrize("active_count", [0, 1, 2])
def test_history_selection_has_no_row_multiplication(catalog_db, source, model, active_count):
    person, position, rank, records = populate(catalog_db)
    original = records[source]
    original.is_active = active_count == 2
    kwargs = {"person_id": person.person_id, "is_active": active_count >= 1}
    if model is PersonName:
        kwargs.update(surname="Активенко", name="Олена")
    if model is PersonRank:
        kwargs.update(rank_id=rank.rank_id, rank_order_number="А-99", rank_order_day=20)
    selected = model(**kwargs)
    # Later created_at must not beat the explicit active flag.
    original.created_at = datetime(2050, 1, 1)
    selected.created_at = datetime(2000, 1, 1)
    catalog_db.add(selected); catalog_db.commit()
    result = Service.get_positions(catalog_db)
    assert result["total"] == result["occupied"] == 1
    row = result["rows"][0]
    assert row[source] is (selected if active_count == 1 else None)
    assert bool(result["data_warnings"]) == (active_count != 1)
    if source == "person_rank" and active_count == 1:
        assert row["values"]["rank"] == rank.nominative
        assert row["values"]["rank_order_number"] == "А-99"
        assert row["values"]["rank_order_date"] == "20._._"


def test_rank_and_order_are_from_same_active_history(catalog_db):
    person, position, rank, records = populate(catalog_db)
    other_rank = make_rank(); other_rank.code="officer"; other_rank.nominative="Офіцер"
    catalog_db.add(other_rank); catalog_db.flush()
    catalog_db.add(PersonRank(person_id=person.person_id, rank_id=other_rank.rank_id, is_active=True,
                             rank_order_number="О-1", rank_order_year=2024))
    catalog_db.commit()
    result = Service.get_positions(catalog_db, column_filters={"rank": ["Офіцер"], "rank_order_number": ["О-1"]})
    assert result["total"] == 1
    assert result["rows"][0]["values"]["rank_order_date"] == "_._.2024"
    assert Service.get_positions(catalog_db, column_filters={"rank": ["Офіцер"], "rank_order_number": ["0012"]})["total"] == 0


@pytest.mark.parametrize("key,value", [("tax_number", "0000000001"), ("full_name", "Тестенко Іван Тестович"),
    ("passport_number", "000123"), ("service_type", "Контракт"), ("rank_order_number", "0012"),
    ("surname_latin", "Testenko"), ("rank_code", "rank-1"), ("name_genitive", "Водій роти"), ("passport_is_active", "0")])
def test_new_scalar_filters_and_cascade(catalog_db, key, value):
    populate(catalog_db)
    catalog_db.add(make_position(2, "Інший", "Медик", "Медик")); catalog_db.commit()
    result = Service.get_positions(catalog_db, column_filters={key: [value], "unit_short": ["Підрозділ"]})
    assert result["total"] == 1
    assert result["filter_options"]["unit_short"] == [{"value": "Підрозділ", "label": "Підрозділ"}]
    assert Service.get_positions(catalog_db, column_filters={key: ["does-not-exist"]})["total"] == 0


@pytest.mark.parametrize("key,parts", [("passport_issued_date", {"years":[2015]}), ("passport_expire_date", {"incomplete_only":True}),
                                      ("service_position_date", {"years":[2019]}), ("service_order_date", {"months":[6]})])
def test_new_dates_use_shared_filter_and_exclude_missing_records(catalog_db, key, parts):
    populate(catalog_db)
    catalog_db.add(make_position(2, "Інший", "Медик", "Медик")); catalog_db.commit()
    result = Service.get_positions(catalog_db, column_filters={key: [DateFilter.from_json(parts).to_json()]})
    assert result["total"] == 1
    assert result["vacant"] == 0


def test_sorting_uses_typed_sql_and_full_name_expression(catalog_db):
    person1, pos1, rank1, records1 = populate(catalog_db, 2)
    person2, pos2, rank2, records2 = populate(catalog_db, 10)
    records1["name"].surname = "Ясенко"; records2["name"].surname = "Андренко"
    records1["passport"].passport_issued_date = date(2020, 1, 1)
    records2["passport"].passport_issued_date = date(1990, 1, 1)
    records1["name"].created_at = datetime(2024, 1, 1)
    records2["name"].created_at = datetime(2020, 1, 1)
    catalog_db.commit()
    numbers = lambda key, direction="asc": [row["position"].position_number for row in Service.get_positions(catalog_db, sort_by=key, direction=direction)["rows"]]
    assert numbers("position_number") == [2, 10]
    for key in ("full_name", "name_created_at", "passport_issued_date"):
        assert numbers(key) == [10, 2]
        assert numbers(key, "desc") == [2, 10]


def test_query_count_is_independent_of_rows_and_field_count(catalog_db):
    populate(catalog_db)
    calls = []
    def record_sql(*args): calls.append(args[2])
    event.listen(catalog_db.bind, "before_cursor_execute", record_sql)
    try:
        Service.get_positions(catalog_db)
        assert len(calls) == 1
        calls.clear()
        for number in range(2, 8):
            populate(catalog_db, number)
        catalog_db.expire_all(); calls.clear()
        result = Service.get_positions(catalog_db)
        assert len(result["rows"]) == 7
        assert len(calls) == 1
        calls.clear()
        Service.get_positions(catalog_db, column_filters={"unit_short": ["Підрозділ"], "passport_number": ["000123"]})
        assert len(calls) == 3  # result + one query per active facet
    finally:
        event.remove(catalog_db.bind, "before_cursor_execute", record_sql)


def test_http_reads_only_allowed_filters_and_preserves_url_contract(catalog_db):
    populate(catalog_db)
    def isolated(): yield catalog_db
    app.dependency_overrides[get_db] = isolated
    try:
        with TestClient(app) as client:
            response = client.get("/person-positions?" + urlencode({"passport_number": "000123", "tax_number": "0000000001",
                "filter_order": "passport_number,tax_number", "sort_by": "name_created_at", "direction": "desc", "sql": "DROP TABLE persons"}))
            assert response.status_code == 200
            ctx = response.context
            assert ctx["total"] == 1
            assert ctx["filter_order"] == "passport_number,tax_number"
            assert "sql" not in ctx["active_filters"]
            assert ctx["sort_by"] == "name_created_at"
            assert "name_created_at" not in ctx["table_column_filters"]["keys"]
            params = parse_qs(ctx["active_query"])
            assert params["passport_number"] == ["000123"]
            assert "data-date-column-key=\"passport_issued_date\"" in response.text
            assert "data-column-key=\"tax_number\"" in response.text
            assert client.get('/person-positions?passport_issued_date=bad').status_code == 400
            assert client.get('/person-positions?service_order_date_priority=year,year,day').status_code == 400
            assert catalog_db.query(Person).count() == 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("parts,expected", [(("", "Іван", "Тестович"), "Іван Тестович"),
    (("Тестенко", "", "Тестович"), "Тестенко Тестович"), (("Тестенко", "Іван", None), "Тестенко Іван"),
    (("", "", ""), "")])
def test_full_name_sql_and_display_agree_for_sparse_values(catalog_db, parts, expected):
    _, _, _, records = populate(catalog_db)
    records["name"].surname, records["name"].name, records["name"].patronymic = parts
    catalog_db.commit()
    assert catalog_db.query(FIELDS["full_name"].expression).scalar() == expected
    token = expected or "__empty__"
    result = Service.get_positions(catalog_db, column_filters={"full_name": [token]})
    assert result["total"] == 1
    assert result["rows"][0]["values"]["full_name"] == (expected or "-")


def test_ambiguous_history_is_reported_in_html_and_people_are_not_duplicated(catalog_db):
    person, _, _, records = populate(catalog_db)
    catalog_db.add(PersonName(person_id=person.person_id, surname="Другенко", name="Тест", is_active=False))
    catalog_db.commit()
    assert len(Service.get_people(catalog_db)) == 1
    assert Service.get_people(catalog_db)[0]["name"] is None
    def isolated(): yield catalog_db
    app.dependency_overrides[get_db] = isolated
    try:
        with TestClient(app) as client:
            response = client.get('/person-positions')
            assert response.status_code == 200
            assert 'data-history-warnings' in response.text
            assert 'записів 2, активних 0' in response.text
            assert response.context["rows"][0]["values"]["surname"] == "-"
            assert response.context["total"] == 1
    finally:
        app.dependency_overrides.clear()


def test_copy_controls_and_header_hide_actions_match_column_capabilities(catalog_db):
    from lxml import html
    populate(catalog_db)
    def isolated(): yield catalog_db
    app.dependency_overrides[get_db] = isolated
    try:
        with TestClient(app) as client:
            response = client.get('/person-positions')
            assert response.status_code == 200
            document = html.fromstring(response.text)
            assert document.xpath('//input[@data-copy-format]/@value') == ['excel', 'word']
            assert document.xpath('//input[@data-copy-format and @checked]/@value') == ['excel']
            assert document.xpath('//button[@data-table-copy and @disabled]')
            assert document.xpath('//script[@src="/static/js/table_selection.js"]')
            for header in document.xpath('//table/thead/tr/th'):
                key = header.get('data-column-key')
                actions = header.xpath('.//button[@data-column-hide]')
                assert len(actions) == (0 if key in ('row_number', 'assignment') else 1), key
                if actions:
                    menu = actions[0].getparent()
                    siblings = list(menu)
                    assert siblings[siblings.index(actions[0])-1].tag == 'hr'
                    if key == 'birth_date':
                        assert menu.get('data-date-menu') is not None
                        assert menu.xpath('.//*[@data-date-sort="asc"]')
    finally:
        app.dependency_overrides.clear()

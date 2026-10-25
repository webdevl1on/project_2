from urllib.parse import parse_qs

import pytest
from starlette.requests import Request

from app.models.person import Person
from app.models.person_identity import PersonName
from app.models.person_military_service import PersonRank
from app.models.person_positions import PersonPosition
from app.models.reference_book import Position, Rank
from app.services.service_person_positions import ServicePersonPositionFunc
from app.routers.person_positions import (
    FILTER_KEYS, build_query_string, get_person_positions_page, normalise_filter_order,
)


def make_position(number, unit, short_name, full_name):
    return Position(
        position_number=number,
        code=f"P{number}",
        unit_short=unit,
        name_short=short_name,
        name_nominative=full_name,
        name_genitive=full_name,
        name_dative=full_name,
        name_accusative=full_name,
        name_instrumental=full_name,
        name_locative=full_name,
        name_vocative=full_name,
    )


def make_rank():
    return Rank(
        code="private",
        nominative="Солдат",
        genitive="Солдата",
        dative="Солдату",
        accusative="Солдата",
        instrumental="Солдатом",
        locative="Солдаті",
        vocative="Солдате",
    )


def test_positions_support_server_filters_and_sorting(db):
    first_position = make_position(20, "Другий", "Стрілець", "Стрілець")
    second_position = make_position(10, "Перший", "Водій", "Водій")
    rank = make_rank()
    person = Person(tax_number=None)
    db.add_all([first_position, second_position, rank, person])
    db.flush()

    db.add(PersonName(person_id=person.person_id, surname="Петренко", name="Петро"))
    db.add(PersonRank(person_id=person.person_id, rank_id=rank.rank_id, is_active=True))
    db.add(PersonPosition(person_id=person.person_id, position_id=first_position.position_id))
    db.commit()

    result = ServicePersonPositionFunc.get_positions(
        db,
        sort_by="position_number",
        direction="asc",
        column_filters={"unit_short": ["Перший", "Другий"]},
    )

    assert [row["position"].position_number for row in result["rows"]] == [10, 20]
    assert result["occupied"] == 1
    assert result["vacant"] == 1
    assert result["total"] == 2
    assert any(option["value"] == "Перший" for option in result["filter_options"]["unit_short"])


def test_positions_keep_occupancy_filter(db):
    position = make_position(10, "Перший", "Водій", "Водій")
    db.add(position)
    db.commit()

    vacant = ServicePersonPositionFunc.get_positions(db, occupancy="vacant")
    occupied = ServicePersonPositionFunc.get_positions(db, occupancy="occupied")

    assert vacant["total"] == 1
    assert occupied["total"] == 0


@pytest.fixture
def positions_data(db):
    soldier = make_rank()
    sergeant = make_rank()
    sergeant.code = "sergeant"
    sergeant.nominative = "Сержант"
    db.add_all([soldier, sergeant])
    db.flush()
    records = [
        (2, "1 взвод", "Водій", "Адамчук", "Іван", soldier, None),
        (10, "1 взвод", "Стрілець", "Бондар", "Петро", sergeant, ""),
        (30, "2 взвод", "Водій", "Коваль", "Микола", soldier, "Іванович"),
    ]
    for number, unit, title, surname, name, rank, patronymic in records:
        position = make_position(number, unit, title, title)
        person = Person()
        db.add_all([position, person])
        db.flush()
        db.add_all([
            PersonName(person_id=person.person_id, surname=surname, name=name,
                       patronymic=patronymic),
            PersonRank(person_id=person.person_id, rank_id=rank.rank_id, is_active=True),
            PersonPosition(person_id=person.person_id, position_id=position.position_id),
        ])
    db.add(make_position(40, "2 взвод", "Медик", "Медик"))
    db.commit()
    return db


def option_values(result, key):
    return {option["value"] for option in result["filter_options"][key]}


def test_cascade_uses_other_filters_and_excludes_own_filter(positions_data):
    result = ServicePersonPositionFunc.get_positions(
        positions_data,
        column_filters={"unit_short": ["1 взвод"], "rank": ["Солдат"]},
    )
    assert [row["position"].position_number for row in result["rows"]] == [2]
    assert option_values(result, "rank") == {"Солдат", "Сержант"}
    assert option_values(result, "unit_short") == {"1 взвод", "2 взвод"}
    assert option_values(result, "surname") == {"Адамчук"}
    assert (result["total"], result["occupied"], result["vacant"]) == (1, 1, 0)


def test_change_and_clear_one_filter_keeps_other_filters(positions_data):
    filters = {"unit_short": ["1 взвод"], "rank": ["Солдат"]}
    filters["rank"] = ["Сержант"]
    changed = ServicePersonPositionFunc.get_positions(positions_data, column_filters=filters)
    assert [row["position"].position_number for row in changed["rows"]] == [10]
    del filters["rank"]
    cleared = ServicePersonPositionFunc.get_positions(positions_data, column_filters=filters)
    assert [row["position"].position_number for row in cleared["rows"]] == [2, 10]
    assert option_values(cleared, "rank") == {"Солдат", "Сержант"}


def test_multiple_values_and_three_column_intersection(positions_data):
    result = ServicePersonPositionFunc.get_positions(
        positions_data,
        column_filters={"unit_short": ["1 взвод", "2 взвод"],
                        "rank": ["Солдат", "Сержант"], "name_short": ["Водій"]},
    )
    assert [row["position"].position_number for row in result["rows"]] == [2, 30]
    assert option_values(result, "rank") == {"Солдат"}
    assert option_values(result, "name_short") == {"Водій", "Стрілець"}


@pytest.mark.parametrize("direction, expected", [("asc", [2, 10]), ("desc", [10, 2])])
def test_numeric_sorting_after_filtering(positions_data, direction, expected):
    result = ServicePersonPositionFunc.get_positions(
        positions_data, direction=direction, column_filters={"unit_short": ["1 взвод"]},
    )
    assert [row["position"].position_number for row in result["rows"]] == expected
    assert [option["value"] for option in result["filter_options"]["position_number"]] == ["2", "10"]


@pytest.mark.parametrize("key", ["unit_short", "name_short", "name_nominative",
                                 "rank", "surname", "name", "patronymic"])
def test_text_sorting_in_both_directions(positions_data, key):
    asc = ServicePersonPositionFunc.get_positions(positions_data, sort_by=key)
    desc = ServicePersonPositionFunc.get_positions(positions_data, sort_by=key, direction="desc")
    mappings = {
        "unit_short": ("position", "unit_short"),
        "name_short": ("position", "name_short"),
        "name_nominative": ("position", "name_nominative"),
        "rank": ("rank", "nominative"),
        "surname": ("name", "surname"), "name": ("name", "name"),
        "patronymic": ("name", "patronymic"),
    }
    model, attribute = mappings[key]
    values = lambda result: [getattr(row[model], attribute) for row in result["rows"]
                             if row[model] and getattr(row[model], attribute) is not None]
    assert values(asc) == sorted(values(asc))
    assert values(desc) == sorted(values(desc), reverse=True)


def test_empty_values_include_null_and_empty_string(positions_data):
    result = ServicePersonPositionFunc.get_positions(
        positions_data, column_filters={"patronymic": ["__empty__"]},
    )
    assert [row["position"].position_number for row in result["rows"]] == [2, 10, 40]
    vacant = ServicePersonPositionFunc.get_positions(positions_data, occupancy="vacant")
    assert option_values(vacant, "rank") == {"__empty__"}
    assert option_values(vacant, "unit_short") == {"2 взвод"}


def test_no_matches_does_not_lose_active_filters(positions_data):
    filters = {"unit_short": ["1 взвод"], "surname": ["Коваль"]}
    result = ServicePersonPositionFunc.get_positions(positions_data, column_filters=filters)
    assert result["rows"] == []
    assert result["total"] == result["occupied"] == result["vacant"] == 0
    assert option_values(result, "rank") == set()
    assert option_values(result, "surname") == {"Адамчук", "Бондар"}
    assert filters == {"unit_short": ["1 взвод"], "surname": ["Коваль"]}


def test_filter_order_survives_sorting_changes_and_reset():
    filters = {"rank": ["Солдат"], "surname": ["Коваль"], "unit_short": ["2 взвод"]}
    order = "rank,surname,unit_short"
    params = parse_qs(build_query_string("position_number", "desc", "occupied", filters, order))
    assert params["filter_order"] == [order]
    assert params["rank"] == ["Солдат"]
    filters["rank"] = ["Сержант"]
    assert normalise_filter_order(order, filters) == ["rank", "surname", "unit_short"]
    del filters["surname"]
    order = ",".join(normalise_filter_order(order, filters))
    assert order == "rank,unit_short"
    filters["surname"] = ["Бондар"]
    assert normalise_filter_order(order, filters) == ["rank", "unit_short", "surname"]


def test_invalid_sort_and_numeric_filter(positions_data):
    result = ServicePersonPositionFunc.get_positions(positions_data, sort_by="unknown")
    assert [row["position"].position_number for row in result["rows"]] == [2, 10, 30, 40]
    result = ServicePersonPositionFunc.get_positions(
        positions_data, column_filters={"position_number": ["invalid"]},
    )
    assert result["total"] == 0


def test_render_keeps_unavailable_selections_and_filter_order(positions_data):
    request = Request({"type": "http", "method": "GET", "path": "/person-positions",
                       "query_string": b"", "headers": []})
    filters = {key: [] for key in FILTER_KEYS}
    filters.update(unit_short=["1 взвод"], surname=["Коваль"])
    response = get_person_positions_page(
        request, occupancy="all", sort_by="position_number", direction="desc",
        filter_order="surname,unit_short", db=positions_data, **filters,
    )
    assert response.status_code == 200
    assert response.context["total"] == 0
    assert response.context["filter_numbers"] == {"surname": 1, "unit_short": 2}
    assert response.context["active_filters"]["surname"] == ["Коваль"]
    assert option_values(response.context, "surname") == {"Адамчук", "Бондар"}
    params = parse_qs(response.context["sort_commands"]["rank"]["asc"].lstrip("?"))
    assert params["surname"] == ["Коваль"]
    assert params["unit_short"] == ["1 взвод"]
    assert params["filter_order"] == ["surname,unit_short"]
    assert "Штатних посад не знайдено." in response.body.decode()


def test_assignment_transfer_and_release_still_work(positions_data):
    db = positions_data
    source = db.query(Position).filter_by(position_number=2).one()
    target = db.query(Position).filter_by(position_number=40).one()
    person_id = db.query(PersonPosition).filter_by(position_id=source.position_id).one().person_id
    from app.services.staff_service import StaffService, assignments_at
    from datetime import date
    on=date(2020,1,1)
    expected=StaffService.assignment_snapshot(db,target.position_id,person_id,on)
    ServicePersonPositionFunc.assign_person_to_position(target.position_id,person_id,db,on=on,expected=expected,confirmed=True)
    assert assignments_at(db,on).filter(PersonPosition.position_id==source.position_id).first() is None
    assert assignments_at(db,on).filter(PersonPosition.person_id==person_id).one().position_id==target.position_id
    release=date(2020,1,2)
    expected=StaffService.assignment_snapshot(db,target.position_id,None,release)
    ServicePersonPositionFunc.assign_person_to_position(target.position_id,None,db,on=release,expected=expected,confirmed=True)
    assert assignments_at(db,release).filter(PersonPosition.position_id==target.position_id).first() is None
    assert db.query(PersonPosition).filter_by(person_id=person_id).count()==2

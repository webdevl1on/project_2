from copy import deepcopy
from app.models.reference_book import Position

from app.routers.person_positions import templates
from app.table_columns import PERSON_POSITIONS_COLUMNS, PERSON_POSITIONS_FIELDS


def test_column_metadata_covers_real_columns_with_unique_keys():
    config = PERSON_POSITIONS_COLUMNS
    groups = config["groups"]
    columns = [column for group in groups for column in group["columns"]]
    assert config["id"] == "person-positions"
    assert len({group["key"] for group in groups}) == len(groups)
    assert len(columns) == len({column["key"] for column in columns}) == len(PERSON_POSITIONS_FIELDS) + 2
    assert sum(column["informational"] for column in columns) == len(PERSON_POSITIONS_FIELDS)
    assert sum(column["default_visible"] for column in columns) == 12
    assert all(not column["default_visible"] for column in groups[-2]["columns"])
    assert [column["key"] for column in columns if column["system"]] == ["row_number"]


def test_table_headers_and_cells_follow_config_order_and_labels():
    # Reorder metadata: cells must stay paired with their stable header keys.
    config = deepcopy(PERSON_POSITIONS_COLUMNS)
    config["groups"].reverse()
    config["groups"][1]["columns"][0]["label"] = "Нова назва з конфігурації"
    config["groups"][1]["columns"][0]["default_visible"] = False
    columns = [column for group in config["groups"] for column in group["columns"]]
    position = Position(
        position_id=1, position_number=10, unit_short="Підрозділ",
        name_short="Посада", name_nominative="Повна назва",
    )
    from lxml import html

    rendered = templates.env.get_template("person_positions.html").render(
        table_columns=config, rows=[{
            "position": position, "rank": None, "name": None, "assignment": None,
            "values": {key: field.display({"position": position}) for key, field in PERSON_POSITIONS_FIELDS.items()},
        }], people=[], total=1, occupied=0, vacant=1,
        active_filters={}, sort_urls={}, filter_numbers={}, sort_commands={},
        active_query="", filter_order="", occupancy="all", sort_by="position_number", direction="asc",
    )
    document = html.fromstring(rendered)
    headers = document.xpath('//table/thead/tr/th')
    cells = document.xpath('//table/tbody/tr/td')
    assert [node.get("data-column-key") for node in headers] == [column["key"] for column in columns]
    assert [node.get("data-column-key") for node in cells] == [column["key"] for column in columns]
    assert "Нова назва з конфігурації" in headers[1].text_content()
    assert headers[1].get("hidden") is not None
    assert cells[1].get("hidden") is not None
    number_cell = next(cell for cell in cells if cell.get("data-column-key") == "position_number")
    assert number_cell.text_content().strip() == "10"
    assert len(document.xpath('//form[@action="/person-positions/assign"]')) == 1


def test_router_exposes_only_existing_filter_keys_to_url_adapter(db):
    from starlette.requests import Request
    from app.routers.person_positions import FILTER_KEYS, get_person_positions_page

    request = Request({"type": "http", "method": "GET", "path": "/person-positions", "query_string": b"", "headers": []})
    response = get_person_positions_page(
        request, occupancy="all", sort_by="position_number", direction="asc",
        filter_order="", db=db, **{key: [] for key in FILTER_KEYS},
    )
    adapter = response.context["table_column_filters"]
    assert adapter["keys"] == list(FILTER_KEYS)
    assert adapter["extra"] == {"occupancy": "all", "mirage":"all"}
    assert "data-column-filters" in response.body.decode()


def test_staff_profile_button_uses_assigned_person_id_and_keeps_values_plain():
    from types import SimpleNamespace
    from lxml import html

    rows = []
    for position_id, assignment in [(91, SimpleNamespace(person_id=987)), (92, None)]:
        values = {key: "-" for key in PERSON_POSITIONS_FIELDS}
        values["full_name"] = "Тестове ПІБ" if assignment else "-"
        rows.append({"position": Position(position_id=position_id, position_number=position_id * 10),
                     "assignment": assignment, "values": values})
    rendered = templates.env.get_template("person_positions.html").render(
        table_columns=PERSON_POSITIONS_COLUMNS, rows=rows, people=[], people_labels={987: "Тестове ПІБ"},
        total=2, occupied=1, vacant=1, active_filters={}, sort_urls={}, filter_numbers={},
        sort_commands={}, active_query="", filter_order="", occupancy="all",
        sort_by="position_number", direction="asc",
    )
    document = html.fromstring(rendered)
    numbers = document.xpath('//tbody/tr/td[@data-column-key="row_number"]')
    assert [cell.xpath('./div/span[@data-column-value]')[0].text for cell in numbers] == ["1", "2"]
    link = numbers[0].xpath('.//a')[0]
    assert link.get("href") == "/person_full_info/987"
    assert link.get("title") == link.get("aria-label") == "Відкрити анкету"
    assert link.xpath('./svg[@aria-hidden="true"]')
    assert not numbers[1].xpath('.//a')
    names = document.xpath('//tbody/tr/td[@data-column-key="full_name"]')
    assert not any(cell.xpath('.//a') for cell in names)
    assert names[0].xpath('./span[@data-column-value]')[0].text == "Тестове ПІБ"

from copy import deepcopy
from types import SimpleNamespace

from app.routers.person_positions import templates
from app.table_columns import PERSON_POSITIONS_COLUMNS


def test_column_metadata_covers_real_columns_with_unique_keys():
    config = PERSON_POSITIONS_COLUMNS
    groups = config["groups"]
    columns = [column for group in groups for column in group["columns"]]
    assert config["id"] == "person-positions"
    assert len({group["key"] for group in groups}) == len(groups)
    assert len(columns) == len({column["key"] for column in columns}) == 13
    assert sum(column["informational"] for column in columns) == 11
    assert [column["key"] for column in columns if not column["default_visible"]] == ["rank_order_date"]
    assert [column["key"] for column in columns if column["system"]] == ["row_number"]


def test_table_headers_and_cells_follow_config_order_and_labels():
    # Reorder metadata: cells must stay paired with their stable header keys.
    config = deepcopy(PERSON_POSITIONS_COLUMNS)
    config["groups"].reverse()
    config["groups"][1]["columns"][0]["label"] = "Нова назва з конфігурації"
    config["groups"][1]["columns"][0]["default_visible"] = False
    columns = [column for group in config["groups"] for column in group["columns"]]
    position = SimpleNamespace(
        position_id=1, position_number=10, unit_short="Підрозділ",
        name_short="Посада", name_nominative="Повна назва",
    )
    from lxml import html

    rendered = templates.env.get_template("person_positions.html").render(
        table_columns=config, rows=[{
            "position": position, "rank": None, "name": None, "assignment": None,
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
    assert adapter["extra"] == {"occupancy": "all"}
    assert "data-column-filters" in response.body.decode()

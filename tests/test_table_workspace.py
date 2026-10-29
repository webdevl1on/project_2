from copy import deepcopy
from app.table_columns import PERSONS_COLUMNS, PERSON_POSITIONS_COLUMNS
from tests.test_name_cases import factory, client


def test_people_configuration_is_independent_and_reuses_catalog_labels():
    before=deepcopy(PERSON_POSITIONS_COLUMNS)
    columns=[c for g in PERSONS_COLUMNS['groups'] for c in g['columns']]
    assert PERSONS_COLUMNS['id']=='persons'
    assert len(columns)==len({c['key'] for c in columns})==7
    assert all(c['default_visible'] for c in columns)
    assert [c['key'] for c in columns]==['person_id','surname','name','tax_number','birth_date','rank','rank_order_number']
    assert PERSON_POSITIONS_COLUMNS==before


def test_people_page_has_shared_controls_empty_table_and_real_navigation(client):
    browser,_=client
    page=browser.get('/persons?sort_by=birth_year&direction=desc')
    assert page.status_code==200
    assert 'id="persons" data-column-table' in page.text
    assert 'data-row-height-custom' in page.text and 'data-selection-mode' in page.text
    assert 'table_appearance.js' in page.text and 'table_workspace.js' in page.text
    assert 'aria-current="page">Люди' in page.text
    assert 'column-toggle' not in page.text.replace('data-column-toggle','')
    assert 'name="direction"' in page.text

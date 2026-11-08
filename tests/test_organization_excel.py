"""Pure XLSX parser tests; no database or working reference files are used."""
from io import BytesIO
from zipfile import ZipFile
import pytest
from openpyxl import Workbook, load_workbook

from app.services.organization_excel import read_positions, empty_template, MAX_INPUT_BYTES
from app.validators.position_validator import POSITION_ATTRIBUTES


def position(number=27, name="Командир відділення"):
    return [number, "CODE", "3 рота", name, *[name] * 7]


def workbook(rows=(), *, children=2, header=None, sheet="positions"):
    book = Workbook()
    ws = book.active
    ws.title = sheet
    ws.append(header or ["parent", *[f"child_{number}" for number in range(1, children + 1)], *POSITION_ATTRIBUTES])
    ws.append(["Цей рядок — пояснення, не дані"])
    for row in rows:
        ws.append(row)
    ignored = book.create_sheet("persons")
    ignored.append(["не імпортувати"])
    stream = BytesIO()
    book.save(stream)
    book.close()
    return stream.getvalue()


def test_six_levels_preserve_names_normalized_keys_and_excel_rows():
    names = [" 3  РОТА ", *[f"Підрозділ {number}" for number in range(1, 7)]]
    result = read_positions(workbook([[None] * 18, [*names, *position()]], children=6), "3 рота")
    assert result["errors"] == []
    row = result["rows"][0]
    assert row["row_number"] == 4
    assert row["path"] == ["3  РОТА", *names[1:]]
    assert row["path_keys"] == ["3 рота", *[name.casefold() for name in names[1:]]]
    assert row["position"]["name_vocative"] == "командир відділення"
    assert row["position"]["code"] == "CODE"


def test_root_only_and_trailing_empty_children():
    result = read_positions(workbook([["3 рота", None, "", *position()]]), "3 рота")
    assert not result["errors"]
    assert result["rows"][0]["path"] == ["3 рота"]


@pytest.mark.parametrize("path,fragment", [
    (["Інша рота", "1 взвод", None], "parent не відповідає"),
    (["3 рота", None, "1 відділення"], "Пропуск у шляху"),
    ([None, "1 взвод", None], "parent обов’язкова"),
    (["3 рота", 7, None], "текст від 1 до 500"),
])
def test_invalid_paths_are_retained_as_conflicts(path, fragment):
    result = read_positions(workbook([[*path, *position()]]), "3 рота")
    assert len(result["rows"]) == 1
    assert result["rows"][0]["errors"]
    assert any("Рядок 3:" in message and fragment in message for message in result["errors"])


def test_duplicate_number_different_path_flags_every_candidate():
    result = read_positions(workbook([
        ["3 рота", "1 взвод", None, *position()],
        ["3 рота", "2 взвод", None, *position()],
        ["3 рота", "1 взвод", None, *position(28)],
    ]), "3 рота")
    assert len(result["rows"]) == 3
    assert all("Конфлікт номера" in row["errors"][0] for row in result["rows"][:2])
    assert result["rows"][2]["errors"] == []
    assert all("3, 4" in message for message in result["errors"])


def test_duplicate_number_different_requisites_remains_a_conflict():
    result = read_positions(workbook([
        ["3 рота", None, None, *position()],
        ["3 рота", None, None, *position(name="Інша посада")],
    ]), "3 рота")
    assert len(result["rows"]) == 2
    assert len(result["errors"]) == 2


def test_identical_rows_have_explicit_duplicate_reference_without_second_guess():
    result = read_positions(workbook([
        ["3 рота", "1 взвод", None, *position()],
        ["3 РОТА", "1 ВЗВОД", None, *position()],
    ]), "3 рота")
    assert not result["errors"]
    assert result["rows"][1]["duplicate_of"] == 3
    assert "Рядок 4:" in result["warnings"][0]


@pytest.mark.parametrize("change,fragment", [
    (lambda h: h + ["parent"], "Повторні"),
    (lambda h: h[1:], "parent"),
    (lambda h: ["child_3" if value == "child_2" else value for value in h], "без пропусків"),
    (lambda h: ["child_0" if value == "child_2" else value for value in h], "Некоректна"),
    (lambda h: h + ["unexpected"], "колонка"),
    (lambda h: ["" if value == "code" else value for value in h], "Порожня"),
])
def test_structural_header_errors_are_rejected(change, fragment):
    header = ["parent", "child_1", "child_2", *POSITION_ATTRIBUTES]
    with pytest.raises(ValueError, match=fragment.lower() if fragment == "Некоректна" else fragment):
        read_positions(workbook(header=change(header)), "3 рота")


def test_worksheet_is_required_and_other_worksheets_are_ignored():
    with pytest.raises(ValueError, match="positions відсутній"):
        read_positions(workbook(sheet="wrong"), "3 рота")
    result = read_positions(workbook([["3 рота", None, None, *position()]]), "3 рота")
    assert len(result["rows"]) == 1


@pytest.mark.parametrize("value", ["помилка", 0, 1.5, True])
def test_invalid_position_rows_have_physical_row_number(value):
    result = read_positions(workbook([["3 рота", None, None, *position(value)]]), "3 рота")
    assert len(result["rows"])==1 and not result['rows'][0]['position_valid']
    assert result["errors"][0].startswith("Рядок 3:")


def test_path_keys_use_the_same_nfc_as_organization_names():
    import unicodedata
    name='Окремий підрозділ'
    result=read_positions(workbook([[unicodedata.normalize('NFD',name),None,None,*position()]]),name)
    assert result['errors']==[] and result['rows'][0]['path_keys']==[name.casefold()]


def test_upload_and_expanded_limits_and_invalid_zip_are_rejected():
    with pytest.raises(ValueError, match="5 МБ"):
        read_positions(b"x" * (MAX_INPUT_BYTES + 1), "3 рота")
    with pytest.raises(ValueError, match="прочитати"):
        read_positions(b"not XLSX", "3 рота")
    stream = BytesIO()
    from zipfile import ZIP_DEFLATED
    with ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("expanded.txt", b"0" * (50 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="50 МБ"):
        read_positions(stream.getvalue(), "3 рота")


def test_empty_rows_and_explanatory_row_are_never_dictionary_records():
    result = read_positions(workbook([[None] * 14, [" "] * 14]), "3 рота")
    assert result["rows"] == []
    assert result["errors"] == ["Немає коректних посад для імпорту."]


def test_template_has_six_dynamic_children_and_explanatory_second_row():
    book = load_workbook(BytesIO(empty_template(6)), read_only=True)
    try:
        ws = book["positions"]
        header = [cell.value for cell in ws[1]]
        assert header == ["parent", *[f"child_{i}" for i in range(1, 7)], *POSITION_ATTRIBUTES]
        assert ws.max_row == 2
        assert ws[2][0].value == "Вибраний кореневий підрозділ"
    finally:
        book.close()


@pytest.mark.parametrize("depth", [-1, 1.5, True, 20000])
def test_template_rejects_invalid_depth(depth):
    with pytest.raises(ValueError):
        empty_template(depth)

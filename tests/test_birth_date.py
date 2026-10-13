import pytest

from app.utils.date_utils import format_partial_date, validate_date_components
from app.services.service_person_create import ServicePersonCreate


def test_validate_full_birth_date():
    result = validate_date_components("11", "01", "1966", full=True)

    assert result.day == 11
    assert result.month == 1
    assert result.year == 1966


@pytest.mark.parametrize(
    ("day", "month", "year", "expected"),
    [
        (None, None, None, ""),
        ("11", "01", "1966", "11.01.1966"),
        (None, "11", "1966", "11.1966"),
        ("03", "11", None, "03.11."),
        ("03", None, None, "03."),
        (None, "03", None, ".03."),
        ("03", None, "1969", "03._.1969"),
        (None, None, "1966", "1966"),
    ],
)
def test_format_partial_birth_date(day, month, year, expected):
    assert format_partial_date(day, month, year) == expected


def test_empty_date_is_allowed_when_not_full():
    assert validate_date_components(full=False).as_dict() == {
        "birth_day": None,
        "birth_month": None,
        "birth_year": None,
    }


def test_full_date_requires_all_components():
    with pytest.raises(ValueError):
        validate_date_components(month="01", year="1966", full=True)


@pytest.mark.parametrize(
    ("day", "month", "year"),
    [("31", "04", "2020"), ("29", "02", "2021"), ("00", "01", "2020")],
)
def test_invalid_calendar_date_is_rejected(day, month, year):
    with pytest.raises(ValueError):
        validate_date_components(day, month, year)


def test_partial_february_allows_day_29_without_year():
    result = validate_date_components("29", "02", None)

    assert result.day == 29


def test_create_person_with_partial_birth_date(db):
    person = ServicePersonCreate.create_person(
        {
            "surname": "Іваненко",
            "name": "Іван",
            "patronymic": None,
            "surname_latin": None,
            "name_latin": None,
            "patronymic_latin": None,
            "tax_number": None,
            "birth_day": None,
            "birth_month": "11",
            "birth_year": "1966",
        },
        db,
    )

    assert person.birth_day is None
    assert person.birth_month == 11
    assert person.birth_year == 1966


def test_update_person_birth_date_keeps_partial_components(db):
    person = ServicePersonCreate.create_person(
        {
            "surname": "Іваненко",
            "name": "Іван",
            "patronymic": None,
            "surname_latin": None,
            "name_latin": None,
            "patronymic_latin": None,
            "tax_number": None,
            "birth_day": "11",
            "birth_month": "01",
            "birth_year": "1966",
        },
        db,
    )

    updated = ServicePersonCreate.update_person(
        person.person_id,
        {
            "surname": "Іваненко",
            "name": "Іван",
            "patronymic": None,
            "surname_latin": None,
            "name_latin": None,
            "patronymic_latin": None,
            "tax_number": None,
            "birth_day": None,
            "birth_month": "11",
            "birth_year": "1966",
        },
        db,
    )

    assert updated.birth_day is None
    assert updated.birth_month == 11
    assert updated.birth_year == 1966

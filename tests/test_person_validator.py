from unittest import result

import pytest
from datetime import date
from app.models.person import Person
from app.validators.person_validator import PersonValidator

#test person pib
def test_validate_person_pib_ok():
    result = PersonValidator.validate_person_pib(
        'Іванов Іван Іванович'    )
    assert result == 'Іванов Іван Іванович'
def test_validate_person_pib_strip():
    result = PersonValidator.validate_person_pib('      Іванов Іван Іванович    ')
    assert result == 'Іванов Іван Іванович'
def test_validate_person_pib_empty():
    with pytest.raises(ValueError):
        PersonValidator.validate_person_pib("")
def test_validate_person_pib_spaces():
    with pytest.raises(ValueError):
        PersonValidator.validate_person_pib("              ")
def test_validate_person_pib_max_symbols():
    with pytest.raises(ValueError):
        PersonValidator.validate_person_pib("a"*256)

#test person rank
def test_validate_person_rank_ok():
    result = PersonValidator.validate_person_rank("soldatasdqwe")
    assert result == "soldatasdqwe"
def test_validate_person_rank_max_symbols():
    with pytest.raises(ValueError):
        PersonValidator.validate_person_rank("a"*101)
def test_validate_person_rank_strip():
    result = PersonValidator.validate_person_rank('     soldat     ')
    assert result == 'soldat'
def test_validate_person_rank_empty():
    result = PersonValidator.validate_person_rank("")
    assert result is None
def test_validate_person_rank_none():
    result = PersonValidator.validate_person_rank(None)
    assert result is None

#test person birth date
def test_validate_person_birth_date_ok():
    result = PersonValidator.validate_date("15.06.2026")
    assert result == date(2026, 6, 15)
def test_validate_person_birth_date_empty():
    result = PersonValidator.validate_date("")
    assert result is None
def test_validate_person_birth_date_none():
    result = PersonValidator.validate_date(None)
    assert result is None
def test_validate_person_birth_date_invalid():
    with pytest.raises(ValueError):
        PersonValidator.validate_date("2025-01-15")

#test person phone
def test_validate_person_phone_ok():
    result = PersonValidator.validate_person_phone("+38098989875")
    assert result == "+38098989875"
def test_validate_person_phone_strip():
    result = PersonValidator.validate_person_phone("   +387512231     ")
    assert result == "+387512231"
def test_validate_person_phone_none():
    result = PersonValidator.validate_person_phone(None)
    assert result is None
def test_validate_person_phone_too_long():
    with pytest.raises(ValueError):
        PersonValidator.validate_person_phone("+123456789012345678901")

#test person name
def test_validate_names_ok():
    result = PersonValidator.validate_names("Василь")
    assert result == "Василь"
def test_validate_names_too_long():
    with pytest.raises(ValueError):
        PersonValidator.validate_names('a'*101)
def test_validate_names_supports_short_real_names():
    assert PersonValidator.validate_names("Ян") == "Ян"
def test_validate_names_preserves_original_case():
    result = PersonValidator.validate_names("          ваСИЛЬ         ")
    assert result == "ваСИЛЬ"

#test person passport
def test_validate_passport_type_ok_id():
    result = PersonValidator.validate_passport_type("     Id     ")
    assert result == 'id'
def test_validate_passport_type_ok_book():
    result = PersonValidator.validate_passport_type("     bOOk ")
    assert result == 'book'
def test_validate_passport_type_raise():
    with pytest.raises(ValueError):
        PersonValidator.validate_passport_type("type")

def test_validate_passport_series_id_ok():
    result = PersonValidator.validate_passport_series_id(None)
    assert result is None
def test_validate_passport_series_id_ok_blank():
    result = PersonValidator.validate_passport_series_id("       ")
    assert result is None
def test_validate_passport_series_id_raise():
    with pytest.raises(ValueError):
        PersonValidator.validate_passport_series_id("AS")

def test_validate_passport_number_id_ok():
    result= PersonValidator.validate_passport_number_id("123456789")
    assert result == "123456789"
def test_validate_passport_number_id_ok_strip():
    result= PersonValidator.validate_passport_number_id("    123456789    ")
    assert result == "123456789"
def test_validate_passport_number_id_none():
    result= PersonValidator.validate_passport_number_id(None)
    assert result is None
def test_validate_passport_number_id_none_blank():
    result= PersonValidator.validate_passport_number_id("    ")
    assert result is None
def test_validate_passport_number_id_letters():
    with pytest.raises(ValueError):
        PersonValidator.validate_passport_number_id("1234a6789")
def test_validate_passport_number_id_long():
    with pytest.raises(ValueError):
        PersonValidator.validate_passport_number_id("1234567890")
def test_validate_passport_number_id_short():
    with pytest.raises(ValueError):
        PersonValidator.validate_passport_number_id("1234")

def test_validate_passport_issued_by_id_ok():
    result = PersonValidator.validate_issued_by_id("0124")
    assert result == "0124"
def test_validate_passport_issued_by_id_strip():
    result = PersonValidator.validate_issued_by_id("      0124    ")
    assert result == "0124"
def test_validate_passport_issued_by_id_none():
    result = PersonValidator.validate_issued_by_id(None)
    assert result is None
def test_validate_passport_issued_by_id_none_blank():
    result = PersonValidator.validate_issued_by_id("            ")
    assert result is None
def test_validate_passport_issued_by_id_letter():
    with pytest.raises(ValueError):
        PersonValidator.validate_issued_by_id("12a4")
def test_validate_passport_issued_by_id_long():
    with pytest.raises(ValueError):
        PersonValidator.validate_issued_by_id("12345")
def test_validate_passport_issued_by_id_short():
    with pytest.raises(ValueError):
        PersonValidator.validate_issued_by_id("123")


def test_validate_passport_series_book_ok():
    result = PersonValidator.validate_passport_series_book("ав")
    assert result == "АВ"
def test_validate_passport_series_book_ok_none():
    result = PersonValidator.validate_passport_series_book(None)
    assert result is None
def test_validate_passport_series_book_ok_none_blank():
    result = PersonValidator.validate_passport_series_book("    ")
    assert result is None
def test_validate_passport_series_book_raise():
    with pytest.raises(ValueError):
        PersonValidator.validate_passport_series_book("ASD")

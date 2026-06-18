from unittest import result

import pytest
from datetime import date
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
    result = PersonValidator.validate_person_birth_date("15.06.2026")
    assert result == date(2026, 6, 15)
def test_validate_person_birth_date_empty():
    result = PersonValidator.validate_person_birth_date("")
    assert result is None
def test_validate_person_birth_date_none():
    result = PersonValidator.validate_person_birth_date(None)
    assert result is None
def test_validate_person_birth_date_invalid():
    with pytest.raises(ValueError):
        PersonValidator.validate_person_birth_date("2025-01-15")

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

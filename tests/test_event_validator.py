from unittest import result

import pytest
from datetime import date
from app.validators.event_validatotor import EventValidator



#test event name
def test_validate_event_name_ok():
    result = EventValidator.validate_event_name(
        "Відпустка"
    )
    assert result == "Відпустка"
def test_validate_event_name_strip():
    result = EventValidator.validate_event_name(
        "  Відпустка нова    "
    )
    assert result == "Відпустка нова"
def test_validate_event_name_empty():
    with pytest.raises(ValueError):
        EventValidator.validate_event_name("")
def test_validate_event_name_spaces():
    with pytest.raises(ValueError):
        EventValidator.validate_event_name("    ")
def test_validate_event_name_max_symbols():
    with pytest.raises(ValueError):
        EventValidator.validate_event_name("a"*256)

#test event date
def test_validate_event_date_ok():
    result = EventValidator.validate_event_date("15.06.2026")
    assert result == date(2026, 6, 15)
def test_validate_event_date_empty():
    result = EventValidator.validate_event_date("")
    assert result is None
def test_validate_event_date_none():
    result = EventValidator.validate_event_date(None)
    assert result is None
def test_validate_event_date_invalid():
    with pytest.raises(ValueError):
        EventValidator.validate_event_date("2025-01-15")

#test event duration
def test_validate_event_duration_ok():
    result = EventValidator.validate_event_duration("20")
    assert result == 20
    assert isinstance(result, int)
def test_validate_event_duration_int():
    result = EventValidator.validate_event_duration(20)
    assert result == 20
    assert isinstance(result, int)
def test_validate_event_duration_empty():
    result = EventValidator.validate_event_duration("")
    assert result is None
def test_validate_event_duration_none():
    result = EventValidator.validate_event_duration(None)
    assert result is None
def test_validate_event_duration_negative():
    with pytest.raises(ValueError):
        EventValidator.validate_event_duration("-10")
def test_validate_event_duration_negative_int():
    with pytest.raises(ValueError):
        EventValidator.validate_event_duration(-10)
def test_validate_event_duration_zero():
    with pytest.raises(ValueError):
        EventValidator.validate_event_duration("0")
def test_validate_event_duration_zero_int():
    with pytest.raises(ValueError):
        EventValidator.validate_event_duration(0)
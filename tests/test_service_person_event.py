from unittest import result

import pytest
from datetime import date
from app.database.db import SessionLocal
from app.services.service_for_person_event import PersonEventService

#test get_person_or_raise
def test_get_person_or_raise_ok():
    db = SessionLocal()
    result = PersonEventService.get_person_or_raise(5, db)
    assert result is True
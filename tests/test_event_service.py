from unittest import result

import pytest
from datetime import date
from app.services.service_validator_person import PersonService

def test_prepare_new_person_ok():
    person =  PersonService.prepare_new_person(
        pib = "   Іванов Іван Іванович   ",
        rank = "  солдат   ")
    assert person.pib == "Іванов Іван Іванович"
    assert person.rank == "солдат"

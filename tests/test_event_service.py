from unittest import result

import pytest
from datetime import date
from app.services.service_for_person import PersonService

def tes1t1_prepare_new_person_ok():
    person =  PersonService.prepare_new_person(
        pib = "   Іванов Іван Іванович   ",
        rank = "  солдат   ")
    assert person.pib == "Іванов Іван Іванович"
    assert person.rank == "солдат"

from app.models.person_identity import PersonName
from app.services.service_person_create import ServicePersonCreate
from app.services.service_person_name import ServicePersonNameFunc

def test_create_person_without_tax_number_and_birth_date(db):
    data = {
        "tax_number": None,
        "birth_day": None,
        "birth_month": None,
        "birth_year": None,
        "surname": "Іваненко",
        "name": "Іван",
        "patronymic": None,
        "surname_latin": None,
        "name_latin": None,
        "patronymic_latin": None,
    }
    person = ServicePersonCreate.create_person(data, db)
    assert person.person_id is not None
    assert person.tax_number is None
    assert person.birth_day is None
    assert person.birth_month is None
    assert person.birth_year is None
    person_name = (db.query(PersonName)
                   .filter(PersonName.person_id == person.person_id)
                   .one())
    
    assert person_name.surname == "Іваненко"
    assert person_name.name == "Іван"
    assert person_name.is_active is True

def test_create_person_with_tax_number_and_birth_date(db):
    data = {
        "tax_number": "0123456789",
        "birth_day": "01",
        "birth_month": "12",
        "birth_year": "1990",
        "surname": "Петренко",
        "name": "Петро",
        "patronymic": "Петрович",
        "surname_latin": None,
        "name_latin": None,
        "patronymic_latin": None,
    }
    person = ServicePersonCreate.create_person(data, db)
    assert person.person_id is not None
    assert person.tax_number == "0123456789"
    assert person.birth_day == 1
    assert person.birth_month == 12
    assert person.birth_year == 1990
    person_name = (db.query(PersonName)
                   .filter(PersonName.person_id == person.person_id)
                   .one())
    
    assert person_name.surname == "Петренко"
    assert person_name.name == "Петро"
    assert person_name.patronymic == "Петрович"
    assert person_name.is_active is True

def test_change_person_name_creates_name_history(db):
    person_data = {
        "tax_number": None,
        "birth_day": None,
        "birth_month": None,
        "birth_year": None,
        "surname": "Іваненко",
        "name": "Іван",
        "patronymic": "Петрович",
        "surname_latin": None,
        "name_latin": None,
        "patronymic_latin": None,
    }

    person = ServicePersonCreate.create_person(person_data, db)

    updated_name_data = {
        "surname": "Петренко",
        "name": "Іван",
        "patronymic": "Петрович",
        "surname_latin": None,
        "name_latin": None,
        "patronymic_latin": None,
    }

    new_name = ServicePersonNameFunc.add_new_name(
        person_id=person.person_id,
        data=updated_name_data,
        db=db,
    )

    all_names = (
        db.query(PersonName)
        .filter(PersonName.person_id == person.person_id)
        .order_by(PersonName.person_name_id)
        .all()
    )

    assert len(all_names) == 2

    old_name = all_names[0]
    assert old_name.surname == "Іваненко"
    assert old_name.name == "Іван"
    assert old_name.is_active is False

    assert new_name.surname == "Петренко"
    assert new_name.name == "Іван"
    assert new_name.patronymic == "Петрович"
    assert new_name.is_active is True


def test_update_person_name_updates_old_record_without_new_history(db):
    person_data = {
        "tax_number": None,
        "birth_day": None,
        "birth_month": None,
        "birth_year": None,
        "surname": "Іваненко",
        "name": "Іван",
        "patronymic": "Петрович",
        "surname_latin": None,
        "name_latin": None,
        "patronymic_latin": None,
    }

    person = ServicePersonCreate.create_person(person_data, db)
    new_name = ServicePersonNameFunc.add_new_name(
        person_id=person.person_id,
        data={
            "surname": "Петренко",
            "name": "Іван",
            "patronymic": "Петрович",
            "surname_latin": None,
            "name_latin": None,
            "patronymic_latin": None,
        },
        db=db,
    )

    updated_name = ServicePersonNameFunc.update_person_name(
        person_name_id=new_name.person_name_id,
        data={"name": "Марія"},
        db=db,
    )

    all_names = (
        db.query(PersonName)
        .filter(PersonName.person_id == person.person_id)
        .order_by(PersonName.person_name_id)
        .all()
    )

    assert len(all_names) == 2
    assert updated_name.surname == "Петренко"
    assert updated_name.name == "Марія"
    assert updated_name.patronymic == "Петрович"
    assert all_names[0].name == "Іван"

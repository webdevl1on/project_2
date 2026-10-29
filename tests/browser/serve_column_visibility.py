"""Browser-test server: real routes with generated data in an in-memory database."""

from copy import deepcopy
import sys

from fastapi.responses import HTMLResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import uvicorn

from app.database.base import Base
from app.database.db import get_db
from app.main import app
from app.models import Person, PersonName, PersonPosition, PersonRank, Passport, PersonServiceHistory
from app.routers.person_positions import templates
from tests.test_person_positions import make_position, make_rank


engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
from tests.staff_fixtures import install_legacy_staff_fixture
install_legacy_staff_fixture()
Session = sessionmaker(bind=engine, info={"legacy_staff_fixture":True})
def reset_data():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with Session() as db:
        positions = [
            make_position(10, "Перший", "Водій", "Командир відділення безпілотних комплексів"),
            make_position(20, "Перший", "Стрілець", "Стрілець"),
            make_position(30, "Другий", "Медик", "Медик"),
        ]
        rank = make_rank()
        people = [Person(tax_number="0000000001", birth_day=15, birth_month=3, birth_year=1993),
                  Person(tax_number="0000000002", birth_day=15, birth_month=None, birth_year=1993)]
        db.add_all([*positions, rank, *people])
        db.flush()
        for person, position, surname in zip(people, positions, ("Альфа", "Бета")):
            db.add_all([
                PersonName(person_id=person.person_id, surname=surname, name="Тест"),
                PersonRank(person_id=person.person_id, rank_id=rank.rank_id),
                PersonPosition(person_id=person.person_id, position_id=position.position_id),
            ])
        db.add_all([
            Passport(person_id=people[0].person_id, passport_type="Тестовий", passport_number="000123",
                     passport_issued_by="Тестовий орган", passport_issued_year=2015, is_active=False),
            Passport(person_id=people[1].person_id, passport_number="000456", passport_issued_day=20,
                     passport_issued_month=6, passport_issued_year=2020, is_active=True),
            Passport(person_id=people[1].person_id, passport_number="OLD", is_active=False),
            PersonServiceHistory(person_id=people[0].person_id, military_unit="Тестова частина", service_type="Контракт",
                                 position_year=2019, is_active=False),
        ])
        free=Person(birth_day=28,birth_month=2,birth_year=2001)
        db.add(free); db.flush()
        db.add_all([PersonName(person_id=free.person_id,surname="Гамма",name="Тест"),
                    PersonRank(person_id=free.person_id,rank_id=rank.rank_id)])
        db.commit()


reset_data()

@app.post("/_column-test/reset")
def reset_fixture():
    reset_data()
    return {"ok":True}


def memory_db():
    with Session() as db:
        yield db


app.dependency_overrides[get_db] = memory_db


@app.get("/_column-test/two-tables", response_class=HTMLResponse)
def two_tables():
    first = {
        "id": "example-first",
        "groups": [{"key": "details", "label": "Дані", "columns": [
            {"key": "title", "label": "Назва", "default_visible": True, "informational": True},
            {"key": "code", "label": "Код", "default_visible": False, "informational": True},
        ]}],
    }
    second = deepcopy(first)
    second["id"] = "example-second"
    return templates.env.from_string('''
        {% from "components/column_visibility.html" import column_visibility %}
        <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css">
        <link rel="stylesheet" href="/static/css/column_visibility.css">
        {% for config in configs %}
            {{ column_visibility(config) }}
            <table id="{{ config.id }}" data-column-table><thead><tr>
            {% for column in config.groups[0].columns %}
                <th data-column-key="{{ column.key }}">{{ column.label }}</th>
            {% endfor %}
            </tr></thead><tbody><tr>
            {% for column in config.groups[0].columns %}
                <td data-column-key="{{ column.key }}">Значення</td>
            {% endfor %}
            </tr></tbody></table>
        {% endfor %}
        <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
        <script src="/static/js/table_state.js"></script>
        <script src="/static/js/column_tree.js"></script>
        <script src="/static/js/column_presets.js"></script>
        <script src="/static/js/column_interactions.js"></script>
        <script src="/static/js/table_filters.js"></script>
        <script src="/static/js/table_history.js"></script>
        <script src="/static/js/table_selection.js"></script>
        <script src="/static/js/column_visibility.js"></script>
    ''').render(configs=[first, second])


@app.post('/_column-test/documents/setup')
def document_accounts():
    # Test-only application module: never registered by app.main in production.
    import os
    from app.services.accounts import create_user
    with Session() as db:
        key=create_user(db,'doc-admin','Тестовий адміністратор',os.environ['PROJECT2_ADMIN_TOKEN'],'admin')
    return {'user_id':key,'person_id':3}


@app.post('/_column-test/many-positions')
def many_positions():
    with Session() as db:
        db.add_all(make_position(number,'Великий підрозділ','Посада','Довга тестова назва посади') for number in range(40,1240,10))
        db.commit()
    return {'ok':True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")

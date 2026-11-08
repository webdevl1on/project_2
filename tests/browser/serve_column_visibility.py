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


import os
browser_database = os.environ.get("PROJECT2_DEV_AUTH_DATABASE") or os.environ.get("PROJECT2_BROWSER_DATABASE")
engine = create_engine("sqlite:///"+browser_database if browser_database else "sqlite://", connect_args={"check_same_thread": False}, **({} if browser_database else {"poolclass":StaticPool}))
from tests.staff_fixtures import install_legacy_staff_fixture
install_legacy_staff_fixture()
Session = sessionmaker(bind=engine, info={"legacy_staff_fixture":True})
def reset_data():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.models.mfa import MfaKeyState
    from app.security.mfa_config import encrypt,MARKER
    with Session() as keys:
        keys.add(MfaKeyState(id=1,ciphertext=encrypt(MARKER)));keys.commit()
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
        from app.seeds.seed_event_types import seed_event_types
        from app.seeds.seed_event_subtypes import seed_event_subtypes
        from app.models import EventType, EventSubtype, PersonEvent
        from datetime import date
        seed_event_types(db); seed_event_subtypes(db)
        old_type=db.query(EventType).filter_by(event_type='DAY_OFF').one()
        old_type.event_is_active=False
        old_sub=db.query(EventSubtype).filter_by(event_subtype='VACATION_OTHER').one()
        old_sub.event_subtype_is_active=False
        db.add_all([PersonEvent(person_id=people[1].person_id,event_type_id=old_type.event_type_id,date_start=date(2000,1,1),date_end=date(2000,1,2),duration=2,completion_confirmed=True),
                    PersonEvent(person_id=people[1].person_id,event_type_id=old_sub.event_type_id,event_subtype_id=old_sub.event_subtype_id,date_start=date(2000,2,1),date_end=date(2000,2,2),duration=2,completion_confirmed=True)])
        db.commit()

        from app.services.accounts import create_user
        create_user(db,'browser-admin','Браузерний тестовий адміністратор',os.environ['PROJECT2_ADMIN_TOKEN'],'admin')

reset_data()

@app.post("/_column-test/reset")
def reset_fixture():
    reset_data()
    return {"ok":True}


@app.post('/_column-test/account-master')
def account_master_fixture():
    # Synthetic, test-server-only equivalent of the explicit CLI promotion.
    from sqlalchemy import select
    from app.models import User
    from app.services import accounts
    with Session() as db:
        user=db.scalar(select(User).where(User.username=='browser-admin'))
        accounts.promote_master(db,user.id,os.environ['PROJECT2_ADMIN_TOKEN'],confirmed=True)
        return {'id':user.id}


def memory_db():
    with Session() as db:
        yield db


app.dependency_overrides[get_db] = memory_db

# Explicit policy for synthetic DB-owner fixtures only. Master has no subject ACL
# in app.main and cannot use an unknown production route as an administrator.
# These handlers exist solely in this test server; cookie/MFA/CSRF stay real.
from fastapi import Request,Depends,HTTPException
from app.security.application import application_access
from app.security.accounts import current_user
async def browser_policy(request:Request,db=Depends(get_db)):
    if request.url.path.startswith('/_column-test/'):
        user=await current_user(request,db)
        if user.role not in ('master','admin'):raise HTTPException(403,'Synthetic fixture requires a system administrator.')
        return
    await application_access(request,db)
app.dependency_overrides[application_access]=browser_policy


@app.post('/_column-test/family-geography')
def family_geography_fixture():
    from app.models import GeoUnit, GeoAlias
    with Session() as db:
        first=GeoUnit(kind='region',name='Тестова область сім’ї',normalized_name='тестова область сім’ї')
        second=GeoUnit(kind='region',name='Інша область сім’ї',normalized_name='інша область сім’ї')
        db.add_all([first,second]);db.flush()
        town=GeoUnit(kind='settlement',name='Місто родини',normalized_name='місто родини',parent_id=first.id)
        db.add(town);db.flush();db.add(GeoAlias(unit_id=town.id,name='Старе місто родини',normalized_name='старе місто родини',historical=True))
        db.commit()
        return {'town':town.id,'region':first.id,'other_region':second.id}


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
    from tests.access_helpers import legacy_user as create_user
    with Session() as db:
        from app.models import User
        from sqlalchemy import select
        actor=db.scalar(select(User.id).where(User.username=='browser-admin'))
        existing=db.scalar(select(User.id).where(User.username=='doc-admin'))
        key=existing or create_user(db,'doc-admin','Тестовий адміністратор',os.environ['PROJECT2_ADMIN_TOKEN'],'admin',actor_id=actor)
    return {'user_id':key,'person_id':3}


@app.post('/_column-test/access/setup')
def access_fixture():
    """Synthetic subjects only; grants are made by the browser through real ACL APIs."""
    from datetime import date
    from sqlalchemy import select
    from app.models import User, Position, StaffVersion, StaffStructure, PersonDocument
    from app.services import accounts, organization, organization_staff, documents, document_files, medical
    from tests.access_helpers import legacy_user
    with Session() as db:
        admin=db.scalar(select(User).where(User.username=='browser-admin'))
        master=legacy_user(db,'acl-master','Synthetic Master',os.environ['PROJECT2_ADMIN_TOKEN'],'admin',actor_id=admin.id)
        accounts.promote_master(db,master,os.environ['PROJECT2_ADMIN_TOKEN'],confirmed=True)
        user=accounts.create_user(db,'acl-user','Synthetic User',os.environ['PROJECT2_ADMIN_TOKEN'],'user',actor_id=admin.id)
        other=accounts.create_user(db,'acl-other','Synthetic Other',os.environ['PROJECT2_ADMIN_TOKEN'],'user',actor_id=admin.id)
        root=organization.OrganizationService.create(db,admin.id,'battalion','ACL батальйон',date(1990,1,1))
        unit=organization.OrganizationService.create(db,admin.id,'company','ACL доступна рота',date(1990,1,1),parent_id=root)
        hidden=organization.OrganizationService.create(db,admin.id,'company','ACL прихована рота',date(1990,1,1),parent_id=root)
        version=db.scalar(select(StaffVersion).order_by(StaffVersion.id))
        structure=db.get(StaffStructure,version.staff_structure_id)
        organization_staff.bind_structure(db,admin.id,structure.id,root,structure.revision)
        positions=list(db.scalars(select(Position).where(Position.staff_version_id==version.id).order_by(Position.position_number)))
        organization_staff.bind_positions(db,admin.id,version.id,[{'position_id':pos.position_id,'revision':pos.revision,'org_unit_id':unit if index<2 else hidden,'managed_unit_id':unit if index==0 else None} for index,pos in enumerate(positions)])
        documents.seed_types(db);db.commit()
        doc=documents.save(db,admin.id,1,'military',{'number':'ACL-SECRET-DOC'})
        file=document_files.attach(db,admin.id,1,doc,db.get(PersonDocument,doc).revision,b'%PDF-1.7 synthetic private file','ACL-private.pdf','front')
        medical.save(db,admin.id,1,'exams',{'status':'NEEDS_EXAM','basis':'OTHER','basis_note':'ACL-SECRET-MEDICAL'})
        return {'user':user,'other':other,'master':master,'admin':admin.id,'root':root,'unit':unit,'hidden':hidden,'positions':[p.position_id for p in positions],'document':doc,'file':file}


@app.post('/_column-test/many-positions')
def many_positions():
    with Session() as db:
        db.add_all(make_position(number,'Великий підрозділ','Посада','Довга тестова назва посади') for number in range(40,1240,10))
        db.commit()
    return {'ok':True}




@app.post('/_column-test/journal-snapshot')
def journal_snapshot_fixture():
    """Synthetic history for the dedicated browser suite; never installed by app.main."""
    from datetime import date
    from app.models import StaffVersion,Position,EventType,PersonEvent,PersonAssignment
    from app.services.staff_service import StaffService
    from app.services import person_events
    with Session() as db:
        old=db.query(StaffVersion).one()
        old_key,structure=old.id,old.staff_structure_id
        db.get(Position,1).position_number=15
        name=db.query(PersonName).filter_by(person_id=1).one()
        name.surname='Надзвичайнодовгетестовепрізвище';name.name='Альфа';name.patronymic='Тестович';db.commit()
        StaffService.close_version(db,old_key,db.get(StaffVersion,old_key).revision,date(2026,10,9))
        version=StaffVersion(staff_structure_id=structure,name='Нова тестова версія',valid_from=date(2026,10,10));db.add(version);db.flush()
        positions=[]
        for number,unit,role in [(27,'Другий','Командир відділення безпілотних комплексів із довгою тестовою назвою'),(28,'Перший','Стрілець'),(29,'Майбутній','Радист')]:
            p=make_position(number,unit,role,role);p.staff_version_id=version.id;db.add(p);positions.append(p)
        db.commit()
        StaffService.create_assignment(db,1,positions[0].position_id,date(2026,10,10))
        StaffService.create_assignment(db,2,positions[1].position_id,date(2026,10,10))
        # Synthetic legacy future record, intentionally not a new service write.
        db.add(PersonAssignment(person_id=3,staff_position_id=positions[2].position_id,assigned_from=date(2026,11,10)));db.commit()
        kinds={r.event_type:r.event_type_id for r in db.query(EventType)}
        person_events.save(db,1,{'event_type_id':kinds['VACATION'],'date_start':'2026-10-05','date_end':'2026-10-15'})
        person_events.save(db,2,{'event_type_id':kinds['VLK'],'date_start':'2026-09-01'})
        return {'today':person_events.today().isoformat(),'name':name.surname+' '+name.name+' '+name.patronymic}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]), log_level="warning")

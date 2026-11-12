"""Additive 0009→0010 transition and PostgreSQL hierarchy/roster guards, project2_ci only."""
from datetime import date as D
from pathlib import Path
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.access_helpers import legacy_user
from app.services.organization import OrganizationService as Service
from app.services.organization_staff import ensure_structure
from app.database.postgresql import require_postgresql_schema
from app.models import StaffVersion

@pytest.mark.parametrize('pg_factory',['0009_access_control'],indirect=True)
def test_upgrade_preserves_legacy_identity_and_leaves_other_level_unknown(pg_factory):
    engine=pg_factory.kw['bind']
    with engine.begin() as db:
        db.execute(text("INSERT INTO org_units(id,kind,formed_on,sort_order,revision,created_at,updated_at) VALUES (101,'company','2020-01-01',0,1,now(),now()),(102,'other','2020-01-01',0,1,now(),now())"))
        db.execute(text("INSERT INTO org_unit_states(org_unit_id,name,normalized_name,primary_parent_id,valid_from,revision,created_at,updated_at) VALUES (101,'Рота','рота',NULL,'2020-01-01',1,now(),now()),(102,'Інший','інший',101,'2020-01-01',1,now(),now())"))
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with engine.begin() as db:
        cfg.attributes['connection']=db;command.upgrade(cfg,'head')
    require_postgresql_schema(engine)
    with engine.connect() as db:
        assert db.execute(text('SELECT id,kind,hierarchy_level FROM org_units ORDER BY id')).all()==[(101,'company',None),(102,'other',None)]
        assert db.scalar(text('SELECT count(*) FROM org_audit'))==0
    with pytest.raises(DBAPIError),engine.begin() as db:
        db.execute(text("INSERT INTO org_units(kind,formed_on,sort_order,revision,created_at,updated_at) VALUES ('other','2020-01-01',0,1,now(),now())"))

@pytest.mark.parametrize('kind',['detachment','battery'])
def test_new_roster_owners_have_independent_versions(pg_factory,kind):
    with pg_factory() as db:
        actor=legacy_user(db,'hierarchy-admin','Тест','synthetic-password','admin')
        key=Service.create(db,actor,kind,'Підрозділ',D(2020,1,1))
        structure=ensure_structure(db,key)
        db.add(StaffVersion(staff_structure_id=structure.id,name='Окрема',valid_from=D(2020,1,1)));db.commit()


def test_sql_primary_hierarchy_rejects_equal_or_reversed_types(pg_factory):
    engine=pg_factory.kw['bind']
    for child_kind in ('regiment','platoon'):
        with pytest.raises(DBAPIError),engine.begin() as db:
            db.execute(text("INSERT INTO org_units(id,kind,formed_on,sort_order,revision,created_at,updated_at) VALUES (101,'platoon','2020-01-01',0,1,now(),now()),(102,:kind,'2020-01-01',0,1,now(),now())"),{'kind':child_kind})
            db.execute(text("INSERT INTO org_unit_states(org_unit_id,name,normalized_name,primary_parent_id,valid_from,revision,created_at,updated_at) VALUES (101,'Батько','батько',NULL,'2020-01-01',1,now(),now()),(102,'Дитина','дитина',101,'2020-01-01',1,now(),now())"))


@pytest.mark.parametrize('pg_factory',['0009_access_control'],indirect=True)
def test_upgrade_refuses_invalid_legacy_hierarchy_without_changing_it(pg_factory):
    engine=pg_factory.kw['bind']
    with engine.begin() as db:
        db.execute(text("INSERT INTO org_units(id,kind,formed_on,sort_order,revision,created_at,updated_at) VALUES (101,'platoon','2020-01-01',0,1,now(),now()),(102,'regiment','2020-01-01',0,1,now(),now())"))
        db.execute(text("INSERT INTO org_unit_states(org_unit_id,name,normalized_name,primary_parent_id,valid_from,revision,created_at,updated_at) VALUES (101,'Взвод','взвод',NULL,'2020-01-01',1,now(),now()),(102,'Полк','полк',101,'2020-01-01',1,now(),now())"))
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with pytest.raises(DBAPIError,match='Correct legacy primary hierarchy'),engine.begin() as db:
        cfg.attributes['connection']=db;command.upgrade(cfg,'head')
    with engine.connect() as db:
        assert db.scalar(text('SELECT version_num FROM alembic_version'))=='0009_access_control'
        assert db.scalar(text('SELECT primary_parent_id FROM org_unit_states WHERE org_unit_id=102'))==101
        assert db.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='org_units' AND column_name='hierarchy_level'"))==0

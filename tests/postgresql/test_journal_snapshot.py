"""Real PostgreSQL snapshot queries and repeatable, non-destructive catalog update."""
from pathlib import Path
from datetime import date
import pytest
from sqlalchemy import text,select,func
from alembic import command
from alembic.config import Config
from app.models import EventType,EventSubtype,PersonEvent
from app.services import event_views
from app.database.postgresql import require_postgresql_schema
from tests.test_journal_snapshot import prepare_snapshot


@pytest.mark.parametrize('existing_vlk',[False,True])
@pytest.mark.parametrize('pg_factory',['0003_event_corrections'],indirect=True)
def test_catalog_migration_preserves_history_and_custom_vlk(pg_factory,existing_vlk):
    engine=pg_factory.kw['bind']
    with engine.begin() as db:
        pid=db.scalar(text("INSERT INTO persons (sex) VALUES ('male') RETURNING person_id"))
        kind=db.scalar(text("INSERT INTO event_types (event_type,event_name,event_is_active) VALUES ('DAY_OFF','Історична назва',true) RETURNING event_type_id"))
        db.execute(text("INSERT INTO person_events (person_id,event_type_id,date_start,date_end,duration,completion_confirmed) VALUES (:p,:t,'2026-01-01','2026-01-01',1,true)"),{'p':pid,'t':kind})
        if existing_vlk:db.execute(text("INSERT INTO event_types (event_type,event_name,event_is_active,event_color) VALUES ('VLK','Власна назва',false,'#123456')"))
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with engine.begin() as db:cfg.attributes['connection']=db;command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    require_postgresql_schema(engine)
    with pg_factory() as db:
        old=db.get(EventType,kind);assert not old.event_is_active and old.event_name=='Історична назва'
        row=db.scalar(select(PersonEvent));assert row.event_type_id==kind and row.date_start==date(2026,1,1) and row.completion_confirmed
        types=db.scalars(select(EventType).where(EventType.event_type=='VLK')).all();assert len(types)==1
        if existing_vlk:assert types[0].event_name=='Власна назва' and not types[0].event_is_active and types[0].event_color=='#123456'
        else:assert types[0].event_name=='ВЛК' and types[0].event_is_active
        assert db.scalar(select(func.count()).select_from(EventSubtype).where(EventSubtype.event_type_id==types[0].event_type_id))==0


def test_postgresql_staff_snapshot_is_independent_of_event_dates(pg_factory):
    _,ids,key=prepare_snapshot(pg_factory)
    with pg_factory() as db:
        result=event_views.journal(db,{'as_of':'2026-10-10','start':'2026-10-01','end':'2026-11-03'})
        assert {p['id'] for p in result['people']}=={ids[0],ids[4]}
        person=next(p for p in result['people'] if p['id']==ids[0]);assert person['position_number']==27 and person['unit']=='2 взвод'
        assert [c['code'] for c in person['cells'][4:15]]==['VACATION']*11
        before=event_views.journal(db,{'as_of':'2026-10-09','start':'2026-10-01','end':'2026-11-03'})
        assert next(p for p in before['people'] if p['id']==ids[0])['position_number']==15
        assert db.get(PersonEvent,key).date_start==date(2026,10,5)
        assert not db.dirty and not db.new

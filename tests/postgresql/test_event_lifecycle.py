"""Additive migration, preservation and transactional lifecycle in project2_ci."""
from pathlib import Path
from datetime import date
import pytest
from sqlalchemy import text, select, func, event
from alembic import command
from alembic.config import Config
from app.models import Person, PersonEvent, EventType
from app.services import person_events as editor
from app.services.event_views import presence_for_people,problems
from app.database.postgresql import require_postgresql_schema


@pytest.mark.parametrize('pg_factory',['0001_postgresql'],indirect=True)
def test_migration_preserves_legacy_periods_and_catalog(pg_factory):
    engine=pg_factory.kw['bind']
    with engine.begin() as db:
        pid=db.scalar(text("INSERT INTO persons (sex) VALUES ('male') RETURNING person_id"))
        kind=db.scalar(text("INSERT INTO event_types (event_type,event_name,event_is_active) VALUES ('SERVICE','Служба',true) RETURNING event_type_id"))
        db.execute(text("INSERT INTO person_events (person_id,event_type_id,date_start,date_end,duration) VALUES (:p,:t,'2026-10-01','2026-10-05',5),(:p,:t,'2026-10-06',NULL,NULL),(:p,:t,'2099-01-01','2099-01-05',5)"),{'p':pid,'t':kind})
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with engine.begin() as db:
        cfg.attributes['connection']=db;command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    require_postgresql_schema(engine)
    with pg_factory() as db:
        rows=db.scalars(select(PersonEvent).order_by(PersonEvent.event_id)).all()
        assert len(rows)==3 and rows[0].date_end==date(2026,10,5) and rows[0].duration==5 and rows[0].completion_confirmed
        assert rows[1].date_end is None and not rows[1].completion_confirmed
        assert rows[2].date_end==date(2099,1,5) and rows[2].duration==5 and not rows[2].completion_confirmed
        assert all(row.planned_end is None for row in rows)
        assert db.scalar(text("SELECT count(*) FROM event_subtypes WHERE event_subtype LIKE 'SERVICE_%'"))==3


def test_planning_confirming_and_failed_completion_are_atomic(pg_factory):
    with pg_factory.begin() as db:
        p=Person(sex='male');v=EventType(event_type='VACATION',event_name='Відпустка');s=EventType(event_type='SERVICE',event_name='Служба');db.add_all([p,v,s]);db.flush();pid,vid,sid=p.person_id,v.event_type_id,s.event_type_id
    with pg_factory() as db:
        key=editor.save(db,pid,{'event_type_id':vid,'date_start':'2026-10-01','planned_end':'2026-10-10'})
        plan=editor.save(db,pid,{'event_type_id':sid,'date_start':'2099-01-01','planned_end':'2099-01-02'})
        assert db.get(PersonEvent,key).date_end is None
        assert presence_for_people(db,[pid],date(2026,10,11))[pid]['code']=='__pending__'
        original=next(r for r in editor.page(db,pid)['events'] if r['event_id']==key)
        def refuse(*args):raise RuntimeError('synthetic completion refusal')
        event.listen(PersonEvent,'before_update',refuse)
        try:
            with pytest.raises(RuntimeError):editor.save(db,pid,{**original,'date_end':'2026-10-10','completion_confirmed':'1'},key)
        finally:event.remove(PersonEvent,'before_update',refuse)
        assert db.get(PersonEvent,key).date_end is None and not db.get(PersonEvent,key).completion_confirmed
        editor.save(db,pid,{**original,'date_end':'2026-10-12','completion_confirmed':'1'},key)
        assert db.get(PersonEvent,key).duration==12
        assert presence_for_people(db,[pid],date(2026,10,13))[pid]['calculated']
        assert db.scalar(select(func.count()).select_from(PersonEvent))==2
        assert problems(db)['items']==[]


def test_concurrent_future_plans_do_not_duplicate_or_close_current_fact(pg_factory):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    with pg_factory.begin() as db:
        p=Person(sex='male');kind=EventType(event_type='VACATION',event_name='Відпустка');db.add_all([p,kind]);db.flush();pid,kid=p.person_id,kind.event_type_id
    with pg_factory() as db:old=editor.save(db,pid,{'event_type_id':kid,'date_start':'2026-10-01'})
    barrier=Barrier(2)
    def save(index):
        with pg_factory() as db:
            barrier.wait(timeout=5)
            try:editor.save(db,pid,{'event_type_id':kid,'date_start':'2099-01-01','planned_end':'2099-01-10','note':str(index)});return 200
            except editor.EventConflictError:return 409
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(save,[1,2]))==[200,409]
    with pg_factory() as db:
        assert db.scalar(select(func.count()).select_from(PersonEvent))==2
        assert db.get(PersonEvent,old).date_end is None and not db.get(PersonEvent,old).completion_confirmed

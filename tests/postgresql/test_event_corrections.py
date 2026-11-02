"""Correction/annulment migration, guards and concurrent writes, only project2_ci."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from pathlib import Path
import pytest
from sqlalchemy import select, func, text, event
from sqlalchemy.exc import DBAPIError
from alembic import command
from alembic.config import Config
from app.models import PersonEvent, PersonEventCorrection
from app.services import person_events as editor, event_views
from app.database.postgresql import require_postgresql_schema
from tests.postgresql.test_person_events import events


@pytest.mark.parametrize('pg_factory',['0002_event_completion'],indirect=True)
def test_additive_migration_keeps_original_records_unannulled(pg_factory):
    engine=pg_factory.kw['bind']
    with engine.begin() as db:
        pid=db.scalar(text("INSERT INTO persons (sex) VALUES ('male') RETURNING person_id"))
        kind=db.scalar(text("INSERT INTO event_types (event_type,event_name) VALUES ('SERVICE','Служба') RETURNING event_type_id"))
        db.execute(text("INSERT INTO person_events (person_id,event_type_id,date_start,planned_end,note) VALUES (:p,:t,'2026-10-01','2026-10-10','original')"),{'p':pid,'t':kind})
    cfg=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    with engine.begin() as db:
        cfg.attributes['connection']=db;command.upgrade(cfg,'head');command.upgrade(cfg,'head')
    require_postgresql_schema(engine)
    with pg_factory() as db:
        row=db.scalar(select(PersonEvent));assert row.note=='original' and row.planned_end.isoformat()=='2026-10-10'
        assert row.annulled_at is row.annulment_reason is row.annulled_by is None
        assert db.scalar(select(func.count()).select_from(PersonEventCorrection))==0
    with pytest.raises(DBAPIError),engine.begin() as db:db.execute(text('DELETE FROM person_events'))
    with pg_factory() as db:assert db.scalar(select(func.count()).select_from(PersonEvent))==1


def test_correction_and_annulment_audit_failures_rollback_and_guard_history(events):
    factory,pid,service,vacation,_=events
    with factory() as db:
        key=editor.save(db,pid,{'event_type_id':vacation,'date_start':'2026-10-01','planned_end':'2026-10-10'})
        original=editor.page(db,pid)['events'][0]
        def refuse(*args):raise RuntimeError('synthetic correction refusal')
        event.listen(PersonEventCorrection,'before_insert',refuse)
        try:
            with pytest.raises(RuntimeError):editor.save(db,pid,{**original,'event_type_id':service,'confirm_type_change':'1'},key)
            assert db.get(PersonEvent,key).event_type_id==vacation
            with pytest.raises(RuntimeError):editor.annul(db,pid,key,{'expected_state':original['expected_state'],'reason':'test'})
            assert db.get(PersonEvent,key).annulled_at is None
        finally:event.remove(PersonEventCorrection,'before_insert',refuse)
        editor.save(db,pid,{**original,'event_type_id':service,'confirm_type_change':'1'},key)
        current=editor.page(db,pid)['events'][0]
        editor.annul(db,pid,key,{'expected_state':current['expected_state'],'reason':'Виправлення помилки'})
        assert db.scalar(select(func.count()).select_from(PersonEventCorrection))==2
        assert event_views.problems(db)['items']==[]
    engine=factory.kw['bind']
    for sql in ["UPDATE person_event_corrections SET operation='annul'",'DELETE FROM person_event_corrections',"UPDATE person_events SET note='rewrite'",'DELETE FROM person_events']:
        with pytest.raises(DBAPIError),engine.begin() as db:db.execute(text(sql))
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(PersonEventCorrection))==2
        assert len(editor.page(db,pid)['annulled'])==1


def test_concurrent_type_correction_and_annulment_never_overwrite_each_other(events):
    factory,pid,service,vacation,_=events
    with factory() as db:
        key=editor.save(db,pid,{'event_type_id':vacation,'date_start':'2026-10-01'})
        original=editor.page(db,pid)['events'][0]
    barrier=Barrier(2)
    def write(operation):
        with factory() as db:
            barrier.wait(timeout=5)
            try:
                if operation=='edit':editor.save(db,pid,{**original,'event_type_id':service,'confirm_type_change':'1'},key)
                else:editor.annul(db,pid,key,{'expected_state':original['expected_state'],'reason':'Помилковий запис'})
                return 200
            except editor.EventConflictError:return 409
    with ThreadPoolExecutor(max_workers=2) as pool:assert sorted(pool.map(write,['edit','annul']))==[200,409]
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(PersonEvent))==1
        assert db.scalar(select(func.count()).select_from(PersonEventCorrection))==1
        row=db.get(PersonEvent,key)
        assert (row.event_type_id==vacation and row.annulled_at is not None) or (row.event_type_id==service and row.annulled_at is None)

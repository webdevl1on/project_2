"""Independent staff snapshot/event range on synthetic isolated databases."""
from datetime import date
import pytest
from sqlalchemy import select,func
from app.models import Person,PersonEvent,StaffVersion,EventType,EventSubtype
from app.services import event_views,person_events
from app.services.staff_service import StaffService
from app.services.service_person_create import ServicePersonCreate
from app.seeds.seed_event_types import seed_event_types
from app.seeds.seed_event_subtypes import seed_event_subtypes
from tests.test_service_transactions import factory,data
from tests.test_person_positions import make_position


@pytest.fixture
def snapshot(factory):
    return prepare_snapshot(factory)


def prepare_snapshot(factory):
    with factory() as db:
        seed_event_types(db);seed_event_subtypes(db);db.commit()
        people=[ServicePersonCreate.create_person(data(surname=name,tax_number=f'012345678{i}'),db).person_id for i,name in enumerate(['Переведений','Безштатний','Майбутній','Колишній','Інший'])]
        structure=StaffService.create_structure(db,'snapshot','Тестова')
        old=StaffVersion(staff_structure_id=structure,name='№1',valid_from=date(2026,1,1),valid_to=date(2026,10,9));new=StaffVersion(staff_structure_id=structure,name='№2',valid_from=date(2026,10,10));db.add_all([old,new]);db.flush()
        positions=[]
        for number,unit,short,version in [(15,'1 взвод','Водій',old),(16,'1 взвод','Стрілець',old),(27,'2 взвод','Командир відділення безпілотних комплексів',new),(28,'2 взвод','Радист',new),(29,'1 взвод','Стрілець',new)]:
            position=make_position(number,unit,short,short);position.staff_version_id=version.id;db.add(position);positions.append(position)
        db.commit();ids=[p.position_id for p in positions]
        StaffService.create_assignment(db,people[0],ids[0],date(2026,1,1),date(2026,10,9))
        StaffService.create_assignment(db,people[0],ids[2],date(2026,10,10))
        StaffService.create_assignment(db,people[2],ids[3],date(2026,11,10))
        StaffService.create_assignment(db,people[3],ids[1],date(2026,6,1),date(2026,6,30))
        StaffService.create_assignment(db,people[4],ids[4],date(2026,10,10))
        vacation=db.scalar(select(EventType).where(EventType.event_type=='VACATION')).event_type_id
        event_id=person_events.save(db,people[0],{'event_type_id':vacation,'date_start':'2026-10-05','date_end':'2026-10-15'})
        return factory,people,event_id


def query(db,**values):return event_views.journal(db,{'as_of':'2026-10-10','start':'2026-10-01','end':'2026-11-03',**values})


def test_official_snapshot_excludes_unassigned_future_and_past_people(snapshot):
    factory,ids,_=snapshot
    with factory() as db:
        result=query(db)
        assert {p['id'] for p in result['people']}=={ids[0],ids[4]}
        assert result['units']==['1 взвод','2 взвод']
        assert all(p['unit']!='Без штатного призначення' for p in result['people'])
        assert query(db,as_of='2025-12-31')['people']==[]
        assert {p['id'] for p in query(db,as_of='2026-11-10')['people']}=={ids[0],ids[2],ids[4]}


def test_transfer_uses_snapshot_position_but_never_clamps_or_moves_event_dates(snapshot):
    factory,ids,event_id=snapshot
    with factory() as db:
        before=[(r.event_id,r.date_start,r.date_end,r.duration) for r in db.scalars(select(PersonEvent))]
        on9=next(p for p in query(db,as_of='2026-10-09')['people'] if p['id']==ids[0])
        on10=next(p for p in query(db)['people'] if p['id']==ids[0])
        assert (on9['unit'],on9['position_number'])==('1 взвод',15)
        assert (on10['unit'],on10['position_number'])==('2 взвод',27)
        assert [c['code'] for c in on9['cells']]==[c['code'] for c in on10['cells']]
        assert [c['code'] for c in on10['cells'][4:15]]==['VACATION']*11
        assert on10['cells'][3]['calculated'] and on10['cells'][15]['calculated']
        assert sum(c['days'] for c in on10['summary'])==34
        assert before==[(r.event_id,r.date_start,r.date_end,r.duration) for r in db.scalars(select(PersonEvent))]
        assert not db.new and not db.dirty


def test_period_can_precede_version_or_follow_snapshot(snapshot):
    factory,ids,_=snapshot
    with factory() as db:
        result=query(db,start='2026-10-05',end='2026-10-06')
        assert next(p for p in result['people'] if p['id']==ids[0])['cells'][0]['code']=='VACATION'
        result=query(db,as_of='2026-10-01',start='2026-10-14',end='2026-10-16')
        person=next(p for p in result['people'] if p['id']==ids[0])
        assert person['position_number']==15 and [c['code'] for c in person['cells']]==['VACATION','VACATION','__base__']


def test_cascade_value_filters_and_calendar_facets_keep_ids_and_totals(snapshot):
    import json
    factory,ids,_=snapshot
    with factory() as db:
        first=query(db)
        key='jf_date:2026-10-05:2026-10-05'
        value=next(p for p in first['people'] if p['id']==ids[0])['cells'][4]['filter_value']
        result=query(db,jf_unit=json.dumps('2 взвод',ensure_ascii=False),**{key:value,'filter_order':'jf_unit,'+key})
        assert [p['id'] for p in result['people']]==[ids[0]]
        assert result['filter_order']==['jf_unit',key]
        assert sum(c['days'] for c in result['people'][0]['summary'])==34
        assert len(first['facets']['jf_unit'])==2
        assert [p['id'] for p in query(db,jf_unit=[json.dumps('1 взвод',ensure_ascii=False),json.dumps('2 взвод',ensure_ascii=False)])['people']]
        assert query(db,jf_name=json.dumps('Не існує'))['people']==[]


def test_day_off_is_legacy_only_vlk_is_independent_and_repeat_seed_preserves_user_names(snapshot):
    from app.models.medical import MedicalExam,PersonnelTask
    factory,ids,_=snapshot
    with factory() as db:
        kinds={r.event_type:r for r in db.scalars(select(EventType))}
        assert not kinds['DAY_OFF'].event_is_active
        assert db.scalar(select(EventSubtype).where(EventSubtype.event_subtype=='SERVICE_DAY_OFF')) is not None
        assert not db.scalars(select(EventSubtype).where(EventSubtype.event_type_id==kinds['VLK'].event_type_id)).all()
        with pytest.raises(ValueError):person_events.save(db,ids[4],{'event_type_id':kinds['DAY_OFF'].event_type_id,'date_start':'2026-10-01'})
        legacy=PersonEvent(person_id=ids[4],event_type_id=kinds['DAY_OFF'].event_type_id,date_start=date(2026,9,1),date_end=date(2026,9,1),completion_confirmed=True);db.add(legacy);db.commit()
        state=next(r for r in person_events.page(db,ids[4])['events'] if r['event_id']==legacy.event_id)
        person_events.save(db,ids[4],{**state,'note':'Історичне виправлення'},legacy.event_id)
        key=person_events.save(db,ids[4],{'event_type_id':kinds['VLK'].event_type_id,'date_start':'2026-10-01','purpose':'Перевірка'})
        assert event_views.presence_for_people(db,[ids[4]],date(2026,10,2))[ids[4]]['code']=='VLK'
        assert any(p['event_id']==key and p['group']=='vlk' for p in event_views.problems(db,on=date(2026,10,16))['items'])
        assert db.scalar(select(func.count()).select_from(MedicalExam))==0 and db.scalar(select(func.count()).select_from(PersonnelTask))==0
        kinds['VLK'].event_name='Змінена користувачем назва';db.commit();seed_event_types(db);seed_event_subtypes(db);db.commit()
        assert db.get(EventType,kinds['VLK'].event_type_id).event_name=='Змінена користувачем назва'
        assert db.scalar(select(func.count()).select_from(EventType).where(EventType.event_type=='VLK'))==1

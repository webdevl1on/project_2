"""Read union only: assignments are never copied into independent service history."""
from datetime import date,timedelta
from app.repositories.service_history_repository import ServiceHistoryRepository as Repo
from app.repositories.person_repository import ProfileRepository,PersonRepository
from app.services.staff_service import write_unit,checked,today
from app.models import Person,PersonServiceHistory
from app.utils.date_utils import date_values_from_input,format_partial_date
from app.date_fields import DATE_FIELDS


def save_historical(db,person_id,data,key=None):
    values={}
    for field in ('military_unit','position','service_type','order_number','note'):
        raw=(data.get(field) or '').strip()
        if len(raw)>(1000 if field=='note' else 250):raise ValueError('Надто довге текстове поле.')
        values[field]=raw or None
    if not values['military_unit'] and not values['position']:raise ValueError('Вкажіть військову частину або історичну посаду.')
    for prefix,policy in [('position','service.position_date'),('end','service.end_date'),('order','service.order_date')]:
        values.update(date_values_from_input(DATE_FIELDS[policy],prefix,data))
    start=(values['position_year'],values['position_month'],values['position_day'])
    end=(values['end_year'],values['end_month'],values['end_day'])
    for begin,finish in zip(start,end):
        if begin is None or finish is None:break
        if finish<begin:raise ValueError('Завершення історичної служби не може передувати початку.')
        if finish>begin:break
    values['is_active']=data.get('is_active') in ('on','true',True)
    with write_unit(db):
        checked(db,Person,person_id)
        record=Repo.historical(db,key) if key else None
        if key and (not record or record.person_id!=person_id or str(record.revision)!=str(data.get('revision'))):raise ValueError('Історичний запис змінився або недоступний.')
        record=record or Repo.add(db,PersonServiceHistory(person_id=person_id))
        for field,value in values.items():setattr(record,field,value)
        db.flush();return record.person_service_history_id


def change_personal_number(db,person_id,value):
    with write_unit(db):
        person=checked(db,Person,person_id);person.personal_number=value;db.flush()


def chronology(db,person_id):
    checked(db,Person,person_id);rows=[]
    for record,position,version in ProfileRepository.assignments(db,person_id):
        release=record.assigned_to+timedelta(days=1) if record.assigned_to and record.assigned_to<date.max and record.completion_reason in ('release','transfer') else None
        rows.append({'source_type':'assignment','source_id':record.id,'position':position.name_nominative,'unit':position.unit_short,
            'version':version.name,'start':record.assigned_from.isoformat(),'end':record.assigned_to.isoformat() if record.assigned_to else None,
            'release_effective':release,'assignment_order':(record.assignment_order_number,record.assignment_order_date),
            'release_order':(record.release_order_number,record.release_order_date),'state':'Поточне' if record.assigned_from<=today()<=(record.assigned_to or date.max) else 'Історичне / майбутнє',
            'actions':['orders','period','release'],'record':record,'position_id':position.position_id,'sort':(record.assigned_from.year,record.assigned_from.month,record.assigned_from.day)})
    for record in Repo.independent(db,person_id):
        show=lambda prefix:format_partial_date(*(getattr(record,prefix+'_'+part) for part in ('day','month','year')))
        rows.append({'source_type':'historical','source_id':record.person_service_history_id,'position':record.position,'unit':record.military_unit,'version':None,
            'start':show('position'),'end':show('end'),'assignment_order':(record.order_number,show('order')),'release_order':(None,None),'state':'Незалежний запис',
            'actions':['historical'],'record':record,'sort':(record.position_year or 0,record.position_month or 0,record.position_day or 0)})
    return sorted(rows,key=lambda row:(row['sort'],row['source_type'],row['source_id']),reverse=True)


def service_record_applies(record,on):
    """Exclude definitely past/future independent periods without filling unknown parts."""
    def relation(prefix):
        parts=tuple(getattr(record,prefix+'_'+part) for part in ('year','month','day'))
        for known,current in zip(parts,(on.year,on.month,on.day)):
            if known is None:return 0
            if known!=current:return -1 if known<current else 1
        return 0
    return relation('position')<=0 and relation('end')>=0

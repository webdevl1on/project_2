"""Read event history independently from current staffing. Does not alter events."""
from datetime import date
from app.repositories.staff_repository import StaffRepository
from app.repositories.event_repository import EventRepository


def event_positions(db,event,window_end=None):
    if window_end is not None and window_end<event.date_start:
        raise ValueError("Кінець перегляду передує події.")
    end=min(event.date_end,window_end) if event.date_end and window_end else (event.date_end or window_end)
    records=StaffRepository.assignment_period_rows(db,event.person_id,event.date_start,end)
    segments=[];gaps=[];cursor=event.date_start
    from datetime import timedelta
    for assignment,position,version in records:
        start=max(event.date_start,assignment.assigned_from)
        finish=min(assignment.assigned_to,end) if assignment.assigned_to and end else (assignment.assigned_to or end)
        if cursor and cursor<start:gaps.append({"from":cursor,"to":start-timedelta(days=1)})
        segments.append({"position_id":position.position_id,"number":position.position_number,"name":position.name_nominative,
                         "version_id":version.id,"version_name":version.name,"from":start,"to":finish})
        cursor=(finish+timedelta(days=1)) if finish and finish<date.max else None
    if cursor is not None and (end is None or cursor<=end):gaps.append({"from":cursor,"to":end})
    return {"event":event,"note":event.note,"positions":segments,"unknown_periods":gaps,
            "position_status":"Інформація про посаду відсутня" if not segments else
                              "Інформація про посаду відсутня для частини періоду" if gaps else "Посади відомі"}


def events_for_people(db,person_ids,start,end):
    from app.services.staff_service import period
    period(start,end)
    return EventRepository.for_people(db,person_ids,start,end)


def events_for_staff(db,version_id,on,start,end):
    people=StaffRepository.person_ids_at_version(db,version_id,on)
    return events_for_people(db,people,start,end)

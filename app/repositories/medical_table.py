"""Whitelisted scalar projections: no multiplication by medical history rows."""
from sqlalchemy import select,func,case
from sqlalchemy.orm import aliased
from app.models import Person,MedicalExam,Injury,Award,DnaSample,PersonnelTask


def count(model,*conditions):
    value=select(func.count()).select_from(model).where(model.person_id==Person.person_id,*conditions).correlate(Person).scalar_subquery()
    return case((Person.person_id.is_not(None),value),else_=None)


def expression(key):
    if key=='pending_exam_count':return count(MedicalExam,MedicalExam.status!='COMPLETED')
    if key=='planned_exam_count':return count(MedicalExam,MedicalExam.status=='PLANNED')
    if key=='needed_exam_count':return count(MedicalExam,MedicalExam.status=='NEEDS_EXAM')
    if key=='injury_count':return count(Injury)
    if key=='latest_injury_date':return select(func.max(Injury.occurred_on)).where(Injury.person_id==Person.person_id).correlate(Person).scalar_subquery()
    if key=='open_task_count':return count(PersonnelTask,PersonnelTask.status=='OPEN')
    if key=='award_count':return count(Award)
    if key.startswith('award_') and key.endswith('_count'):return count(Award,Award.status==key[6:-6].upper())
    if key.startswith('dna_'):
        if key=='dna_count':return count(DnaSample)
        other=aliased(DnaSample)
        latest=select(func.max(other.collected_on)).where(other.person_id==Person.person_id).correlate(Person).scalar_subquery()
        chosen=select(case((func.count()==1,func.min(DnaSample.id)),else_=None)).where(DnaSample.person_id==Person.person_id,DnaSample.collected_on==latest).correlate(Person).scalar_subquery()
        if key=='dna_collected_on':return latest
        return select(getattr(other,key[4:])).where(other.id==chosen).correlate(Person).scalar_subquery()
    raise KeyError(key)

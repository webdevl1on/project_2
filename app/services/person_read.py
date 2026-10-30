"""Read use cases for person pages; no HTTP or template dependencies."""
from app.repositories.person_repository import PersonRepository
from app.services.service_person_checking import ServicePersonCheck


def list_people(db, sort_by="surname", direction="asc"):
    return [{"person": person, "name": name, "rank": rank}
            for person, name, rank in PersonRepository.list_people(db, sort_by, direction)]


def creation_choices(db):
    return PersonRepository.ranks(db)


def person_details(db, person_id, *, include_history=False, include_ranks=False):
    result = {"person": ServicePersonCheck.get_person_or_raise(person_id, db),
              "current_name": PersonRepository.current_name(db, person_id),
              "current_rank": PersonRepository.current_rank(db, person_id)}
    if include_history:
        result["name_history"] = PersonRepository.name_history(db, person_id)
    if include_ranks:
        result["ranks"] = PersonRepository.ranks(db)
    return result


def full_profile(db,person_id):
    from app.repositories.person_repository import ProfileRepository
    from app.models import PersonName,PersonRank
    from app.services.staff_service import today
    from app.services import geography,contacts
    from app.utils.date_utils import format_partial_date
    result={"person":ServicePersonCheck.get_person_or_raise(person_id,db),"ranks":PersonRepository.ranks(db)}
    warnings=[]
    for key,model in [('current_name',PersonName),('current_rank',PersonRank)]:
        rows=ProfileRepository.active_records(db,model,person_id)
        result[key]=rows[0] if len(rows)==1 else None
        if len(rows)>1:warnings.append('Кілька активних записів ПІБ або звання: актуальне значення не визначено.')
    assignments=ProfileRepository.assignments(db,person_id,today())
    result['profile_assignment']=assignments[0] if len(assignments)==1 else None
    if len(assignments)>1:warnings.append('Кілька чинних призначень: поточну посаду не визначено.')
    from app.services import service_bases
    result.update(service_bases.page(db,person_id))
    result['profile_warnings']=warnings
    result['assignment_history']=ProfileRepository.assignments(db,person_id)
    person=result['person'];result['profile_birth']=format_partial_date(person.birth_day,person.birth_month,person.birth_year) if any([person.birth_day,person.birth_month,person.birth_year]) else None
    result.update(geography.page(db,person_id));result.update(contacts.page(db,person_id))
    result['contact_summary']=contacts.summary(result)
    from app.services.service_chronology import chronology
    from app.repositories.service_history_repository import ServiceHistoryRepository
    result['service_chronology']=chronology(db,person_id)
    result['profile_mirages']=ServiceHistoryRepository.mirages(db,person_id=person_id)
    from app.services.medical import active_exam
    from app.medical_catalog import FITNESS, FORM_FIELDS, LABELS, DOCUMENT_ROLES
    result['active_medical_exam'],result['medical_warning']=active_exam(db,person_id)
    result.update(medical_fitness=FITNESS,medical_fields=FORM_FIELDS,medical_labels=LABELS,medical_documents=DOCUMENT_ROLES)
    result['medical_metadata']={'fields':FORM_FIELDS,'labels':LABELS,'documents':DOCUMENT_ROLES,'fitness':FITNESS}
    return result

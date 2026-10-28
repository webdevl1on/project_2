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
    from app.models import PersonName,PersonRank,PersonServiceHistory
    from app.services.staff_service import today
    from app.services import geography,contacts
    from app.utils.date_utils import format_partial_date
    from app.geography import normalize
    result={"person":ServicePersonCheck.get_person_or_raise(person_id,db),"ranks":PersonRepository.ranks(db)}
    warnings=[]
    for key,model in [('current_name',PersonName),('current_rank',PersonRank)]:
        rows=ProfileRepository.active_records(db,model,person_id)
        result[key]=rows[0] if len(rows)==1 else None
        if len(rows)>1:warnings.append('Кілька активних записів ПІБ або звання: актуальне значення не визначено.')
    assignments=ProfileRepository.assignments(db,person_id,today())
    result['profile_assignment']=assignments[0] if len(assignments)==1 else None
    if len(assignments)>1:warnings.append('Кілька чинних призначень: поточну посаду не визначено.')
    services=ProfileRepository.active_records(db,PersonServiceHistory,person_id)
    wording={'contract':'за контрактом','контракт':'за контрактом','за контрактом':'за контрактом',
             'mobilization':'за мобілізацією','мобілізація':'за мобілізацією','за мобілізацією':'за мобілізацією'}
    result['service_wording']=wording.get(normalize(services[0].service_type)) if len(services)==1 else None
    result['profile_warnings']=warnings
    result['assignment_history']=ProfileRepository.assignments(db,person_id)
    person=result['person'];result['profile_birth']=format_partial_date(person.birth_day,person.birth_month,person.birth_year) if any([person.birth_day,person.birth_month,person.birth_year]) else None
    result.update(geography.page(db,person_id));result.update(contacts.page(db,person_id))
    result['contact_summary']=contacts.summary(result)
    return result

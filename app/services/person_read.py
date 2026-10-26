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

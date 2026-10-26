"""Bulk person lookup and display formatting, independent of a particular form."""
from collections import Counter
from app.repositories.person_repository import PersonRepository
from app.utils.date_utils import format_partial_date


def person_options(db, on):
    result=[]
    for person,name,rank,assignment,position in PersonRepository.picker_rows(db, on):
        label=" ".join(value for value in (name.surname,name.name,name.patronymic) if value) if name else "Без ПІБ"
        birth=format_partial_date(person.birth_day,person.birth_month,person.birth_year)
        result.append({"person":person,"name":name,"id":person.person_id,"label":label,
                       "birth":birth,"rank":rank.nominative if rank else "Звання невідоме",
                       "position_id":position.position_id if position else None,
                       "position_number":position.position_number if position else None,
                       "status":f"Призначений · посада № {position.position_number}" if position else "Вільний"})
    duplicates=Counter((item["label"].casefold(),item["birth"]) for item in result)
    for item in result:
        item["disambiguation"] = f"Код запису: {item['id']}" if duplicates[(item["label"].casefold(),item["birth"])]>1 else ""
        item["search"]=" ".join((item["label"],item["birth"])).casefold()
    return sorted(result,key=lambda item:(item["position_id"] is not None,item["label"].casefold(),item["id"]))


def picker_json(options):
    return [{key:value for key,value in item.items() if key not in ("person","name")} for item in options]

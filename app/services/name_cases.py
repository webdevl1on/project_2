"""Explicit forms: a personal snapshot, then a verified dictionary, then unknown."""
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from app.database.transactions import service_transaction
from app.models.name_cases import NameDictionary, PersonNameCases
from app.name_cases import CASES, NAME_PARTS
from app.repositories.name_case_repository import NameCaseRepository as Repository
from app.repositories.person_repository import PersonRepository
from app.validators.name_cases import word, sex, search_key


class NameFormError(ValueError):
    def __init__(self, message, fields=()):
        super().__init__(message)
        self.fields = list(fields)


def dictionary_values(data, *, verified=False):
    if data.get("kind") not in NAME_PARTS:
        raise ValueError("Невідомий тип словника.")
    result = {"kind": data["kind"], "sex": sex(data.get("sex")),
              "base_form": word(data.get("base_form")), "is_verified": verified}
    for case, label in CASES.items():
        try:
            result[case] = word(data.get(case))
        except ValueError as error:
            raise ValueError(f"{label}: {error}") from error
    if result["base_form"] != result["nominative"]:
        raise ValueError("base_form і nominative повинні збігатися, включно з регістром.")
    result["normalized_key"] = search_key(result["base_form"])
    return result


def lookup(db, kind, value, gender):
    if kind not in NAME_PARTS:
        raise ValueError("Невідомий тип словника.")
    gender = sex(gender)
    value = word(value)
    entry = Repository.find(db, kind, gender, search_key(value))
    if entry and entry.is_verified and all(getattr(entry, case) for case in CASES):
        return {"found": True, "forms": {case: getattr(entry, case) for case in CASES},
                "message": "Знайдено перевірений словник. Перевірте форми для цієї людини."}
    return {"found": False, "forms": {},
            "message": "Перевіреного запису немає. Відмінки можна заповнити вручну; невідомі залиште порожніми."}


def resolve(db, person_name, gender):
    """Read without modifying snapshots, dictionaries or the name history."""
    snapshots = {row.kind: row for row in Repository.personal(db, person_name.person_name_id)}
    result = {}
    for kind in NAME_PARTS:
        base = getattr(person_name, kind)
        saved = snapshots.get(kind)
        valid = saved and saved.base_form == base and saved.sex == gender
        entry = Repository.find(db, kind, gender, search_key(base)) if base and gender else None
        forms = {}; sources = {}; warnings = []
        if saved and not valid:
            warnings.append("Персональні форми стосуються іншого слова або статі; потрібна повторна перевірка.")
        if valid and not saved.is_verified:
            warnings.append("Персональні форми не позначено як перевірені.")
        for case in CASES:
            personal = getattr(saved, case) if valid else None
            global_value = getattr(entry, case) if entry and entry.is_verified else None
            known_base = base if case == "nominative" else None
            forms[case] = personal or global_value or known_base
            sources[case] = "personal" if personal else "dictionary" if global_value else "person_name" if known_base else "missing"
        if base and any(value is None for value in forms.values()):
            warnings.append("Деякі відмінки не заповнені й відсутні у перевіреному словнику.")
        result[kind] = {"forms": forms, "sources": sources, "warnings": warnings,
                        "stale": bool(saved and not valid), "saved": saved}
    return result


def save_personal(db, person_name, gender, data):
    """Participates in its caller's transaction. A missing case remains NULL."""
    current = {row.kind: row for row in Repository.personal(db, person_name.person_name_id)}
    for kind, label in NAME_PARTS.items():
        base = getattr(person_name, kind)
        forms = {}
        for case in CASES:
            if case == "nominative":
                forms[case] = base
                continue
            try:
                forms[case] = word(data.get(f"{kind}_{case}"), required=False)
            except ValueError as error:
                raise NameFormError(f"{label}, {CASES[case]}: {error}", [f"{kind}_{case}"]) from error
        has_forms = any(forms[case] for case in CASES if case != "nominative")
        if has_forms and not base:
            raise NameFormError(f"{label}: спочатку заповніть основне слово.", [kind])
        bound = data.get(f"{kind}_bound_base")
        bound_sex = data.get(f"{kind}_bound_sex")
        if has_forms and ((bound and bound != base) or (bound_sex and bound_sex != gender)):
            raise NameFormError(f"{label}: перевірте відмінки після зміни слова або статі.", [kind])
        if not base and kind not in current:
            continue
        verified = data.get(f"{kind}_verified") in (True, "on", "true", "1")
        verified = verified and all(forms.values())
        record = current.get(kind)
        if record is None:
            record = Repository.add(db, PersonNameCases(person_name_id=person_name.person_name_id, kind=kind))
        record.base_form = base or ""
        record.sex = gender
        record.is_verified = verified
        for case, value in forms.items():
            setattr(record, case, value)


def personal_page(db, name_id):
    record = PersonRepository.get_name(db, name_id)
    if record is None:
        raise ValueError("Запис ПІБ не знайдено.")
    person = PersonRepository.get_by_id(db, record.person_id)
    resolved = resolve(db, record, person.sex)
    data = {kind: getattr(record, kind) or "" for kind in NAME_PARTS}
    for kind, values in resolved.items():
        saved = values["saved"]
        data.update({f"{kind}_{case}": (getattr(saved, case) or "") if saved else "" for case in CASES if case != "nominative"})
        data[f"{kind}_verified"] = bool(saved and saved.is_verified and not values["stale"])
        # Keep old binding explicit: the editor must ask before reusing stale forms.
        data[f"{kind}_bound_base"] = saved.base_form if saved else data[kind]
        data[f"{kind}_bound_sex"] = saved.sex if saved else person.sex
    return record, person, resolved, data


def update_personal(db, name_id, data):
    with service_transaction(db):
        record, person, _, _ = personal_page(db, name_id)
        save_personal(db, record, person.sex, data)
        person_id = person.person_id
    return person_id


def save_dictionary(db, data, *, key=None, revision=None, verified=False):
    values = dictionary_values(data, verified=verified)
    try:
        with service_transaction(db, immediate=True):
            record = Repository.get(db, key) if key is not None else None
            if key is not None and (record is None or record.revision != revision):
                raise ValueError("Запис змінився або видалений. Оновіть сторінку перед редагуванням.")
            existing = Repository.find(db, values["kind"], values["sex"], values["normalized_key"])
            if existing and existing.id != key:
                raise ValueError("Запис із таким словом, типом і статтю вже існує.")
            if record is None:
                record = Repository.add(db, NameDictionary())
            for field, value in values.items():
                setattr(record, field, value)
            db.flush()
            result = record.id
        return result
    except (IntegrityError, StaleDataError) as error:
        raise ValueError("Конфлікт збереження словника. Оновіть дані й повторіть дію.") from error


def dictionary_page(db, kind, query="", page=1):
    if kind not in NAME_PARTS or page < 1:
        raise ValueError("Невірний тип словника або сторінка.")
    rows, total = Repository.list(db, kind, search_key(query), page)
    return {"rows": rows, "total": total, "page": page, "kind": kind, "query": query}


def dictionary_record(db, key):
    record = Repository.get(db, key)
    if record is None:
        raise ValueError("Словниковий запис не знайдено.")
    return record

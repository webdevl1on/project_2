"""Table layouts select reusable trusted fields; no SQL is built from client keys."""
from app.table_fields import FIELDS, GROUPS


def _control(key, label, *, system=False):
    return {"key": key, "label": label, "informational": False, "default_visible": True,
            "system": system, "draggable": not system, "resizable": False,
            "min_width": 56, "width": 56 if system else 360, "filterable": False, "sortable": False}


def table_configuration(table_id, selections, *, overrides=None, controls=False):
    """selections: ordered (group_key, field_keys); names/visibility may be overridden.

    Configuration belongs to the server. A field definition can serve several
    tables without mutating the catalogue or another table's settings.
    """
    groups, seen = [], set()
    for group_key, field_keys in selections:
        columns = []
        for key in field_keys:
            if key in seen:
                raise ValueError(f"Повторний ключ колонки: {key}")
            seen.add(key)
            column = FIELDS[key].metadata()
            changes = (overrides or {}).get(key, {})
            if set(changes) - {"label", "default_visible", "width", "min_width"}:
                raise ValueError("Можна перевизначати лише назву, видимість і розміри колонки.")
            column.update(changes)
            columns.append(column)
        groups.append({"key": group_key, "label": GROUPS[group_key], "columns": columns})
    if len({group["key"] for group in groups}) != len(groups):
        raise ValueError("Ключі груп мають бути унікальними.")
    if controls:
        groups.insert(0, {"key": "numbering", "label": "Нумерація", "columns": [_control("row_number", "№", system=True)]})
        groups.append({"key": "assignment", "label": "Призначення", "columns": [_control("assignment", "Призначений військовослужбовець")]})
    return {"id": table_id, "groups": groups}


PERSON_POSITIONS_COLUMNS = table_configuration(
    "person-positions", [(group, [field.key for field in FIELDS.values() if field.group == group]) for group in GROUPS],
    controls=True,
)
PERSON_POSITIONS_FIELDS = {column["key"]: FIELDS[column["key"]]
                          for group in PERSON_POSITIONS_COLUMNS["groups"] for column in group["columns"]
                          if column["key"] in FIELDS}

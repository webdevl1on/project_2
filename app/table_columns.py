"""Display metadata only; list order determines group and column order.

SQL filter/sort allowlists remain independent of this configuration.
"""


def _column(key, label, *, informational=True, default_visible=True, system=False):
    return {
        "key": key,
        "label": label,
        "informational": informational,
        "default_visible": default_visible,
        "system": system,
        "draggable": not system,
        "resizable": informational,
        "min_width": 100 if informational else 56,
        "width": 56 if system else (180 if informational else 360),
    }


PERSON_POSITIONS_COLUMNS = {
    "id": "person-positions",
    "groups": [
        {
            "key": "numbering",
            "label": "Нумерація",
            "columns": [_column("row_number", "№", informational=False, system=True)],
        },
        {
            "key": "position",
            "label": "Штатна посада",
            "columns": [
                _column("position_number", "№ посади за штатом"),
                _column("unit_short", "Взвод / підрозділ"),
                _column("name_short", "Коротка посада"),
                _column("name_nominative", "Повна посада"),
            ],
        },
        {
            "key": "person",
            "label": "Військовослужбовець",
            "columns": [
                _column("rank", "Звання"),
                _column("surname", "Прізвище"),
                _column("name", "Ім'я"),
                _column("patronymic", "По батькові"),
            ],
        },
        {
            "key": "assignment",
            "label": "Призначення",
            "columns": [
                _column(
                    "assignment", "Призначений військовослужбовець",
                    informational=False,
                ),
            ],
        },
    ],
}

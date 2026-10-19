"""Display metadata only; list order determines group and column order.

SQL filter/sort allowlists remain independent of this configuration.
"""
from app.date_fields import BIRTH_DATE, DATE_FIELDS


def _column(key, label, *, informational=True, default_visible=True, system=False, date_field=None):
    column = {
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
    if date_field is not None:
        column["date"] = date_field.metadata()
    return column


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
                _column("full_name", "ПІБ"),
                _column("surname", "Прізвище"),
                _column("name", "Ім'я"),
                _column("patronymic", "По батькові"),
                _column("birth_date", BIRTH_DATE.label, date_field=BIRTH_DATE),
                _column("rank_order_date", DATE_FIELDS["rank.rank_order_date"].label,
                        date_field=DATE_FIELDS["rank.rank_order_date"], default_visible=False),
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

"""Trusted, reusable field catalogue; never resolve model names from a request.

Only these server-declared sources can become SQL expressions. Table layouts
select catalogue keys; HTML receives serializable metadata, never ORM objects.
"""
from dataclasses import dataclass

from sqlalchemy import case, func

from app.date_fields import BIRTH_DATE, DATE_FIELDS, DateField
from app.models.person import Person
from app.models.person_identity import Passport, PersonName
from app.models.person_military_service import PersonRank, PersonServiceHistory
from app.models.reference_book import Position, Rank
from app.utils.date_query import DateBinding
from app.utils.date_utils import DateComponents, format_partial_date, format_system_timestamp


SOURCES = {
    "position": Position, "person": Person, "name": PersonName,
    "person_rank": PersonRank, "rank": Rank, "passport": Passport,
    "service": PersonServiceHistory,
}
GROUPS = {
    "position": "Штатна посада", "rank": "Військове звання",
    "person": "Особисті дані", "service": "Військова служба",
    "documents": "Документи", "system_data": "Системні дані",
}


@dataclass(frozen=True)
class TableField:
    key: str
    label: str
    group: str
    source: str
    attribute: str
    data_type: str = "text"
    default_visible: bool = False
    date_field: DateField | None = None
    prefix: str | None = None

    @property
    def expression(self):
        if self.key == 'full_address':
            from sqlalchemy import select
            from app.models import PersonAddress
            from app.geography import GEO_FIELDS,DETAIL_FIELDS
            fields=(*GEO_FIELDS,'settlement_type',*DETAIL_FIELDS)
            return select(func.formatted_address(*(getattr(PersonAddress,key) for key in fields))).where(PersonAddress.person_id==Person.person_id,PersonAddress.kind=='registration',PersonAddress.is_active.is_(True)).correlate(Person).scalar_subquery()
        if self.key == "full_name":
            value = func.coalesce(PersonName.surname, "")
            for part in (PersonName.name, PersonName.patronymic):
                value = value + case((part.is_not(None) & (part != ""),
                                      case((value != "", " "), else_="") + part), else_="")
            return case((PersonName.person_name_id.is_not(None), value), else_=None)
        return getattr(SOURCES[self.source], self.attribute)

    @property
    def filterable(self):
        # A date-only component filter would discard the time in a timestamp.
        return self.data_type != "datetime"

    @property
    def date_binding(self):
        if self.data_type != "partial_date":
            return None
        model = SOURCES[self.source]
        return DateBinding(self.date_field, *(getattr(model, f"{self.prefix}_{part}") for part in ("day", "month", "year")))

    @property
    def record_id(self):
        return SOURCES[self.source].__mapper__.primary_key[0]

    def value(self, row):
        if self.key == 'full_address':return row.get('full_address')
        record = row.get(self.source)
        if record is None:
            return None
        if self.key == "full_name":
            return " ".join(value for value in (record.surname, record.name, record.patronymic) if value)
        if self.data_type == "partial_date":
            return DateComponents(*(getattr(record, f"{self.prefix}_{part}") for part in ("day", "month", "year")))
        return getattr(record, self.attribute)

    def display(self, row):
        value = self.value(row)
        if value is None or value == "":
            return "-"
        if isinstance(value, DateComponents):
            if all(part is None for part in (value.day, value.month, value.year)):
                return "-"
            return format_partial_date(value.day, value.month, value.year)
        if self.data_type == "datetime":
            return format_system_timestamp(value)
        if self.data_type == "boolean":
            return "Так" if value else "Ні"
        return str(value)

    def metadata(self):
        model = SOURCES[self.source]
        attributes = [f"{self.prefix}_{part}" for part in ("day", "month", "year")] if self.prefix else [self.attribute]
        computed = self.key in ("full_name","full_address")
        result = {
            "key": self.key, "label": self.label, "group": self.group,
            "source": {"model": model.__name__, "attributes": ["surname", "name", "patronymic"] if self.key == "full_name" else ["person_id"] if computed else attributes,
                       "computed": computed},
            "data_type": self.data_type, "default_visible": self.default_visible,
            "nullable": True if computed else any(getattr(model, attr).property.columns[0].nullable for attr in attributes),
            "optional_record": self.source != "position",
            "selection_source": "person_rank" if self.source == "rank" else self.source,
            "historical": self.source in ("name", "person_rank", "passport", "service"),
            "system_data": self.group == "system_data",
            "filterable": self.filterable, "sortable": True,
            "informational": True, "system": False, "draggable": True, "resizable": True,
            "min_width": 100, "width": 180,
        }
        if self.date_field is not None:
            result["date"] = self.date_field.metadata()
        return result


FIELDS = {}


def _add(key, label, group, source, attribute=None, **kwargs):
    if key in FIELDS:
        raise ValueError(f"Повторний ключ колонки: {key}")
    FIELDS[key] = TableField(key, label, group, source, attribute or key, **kwargs)


_add("position_number", "№ посади за штатом", "position", "position", data_type="integer", default_visible=True)
_add("unit_short", "Взвод / підрозділ", "position", "position", default_visible=True)
_add("name_short", "Коротка посада", "position", "position", default_visible=True)
_add("name_nominative", "Повна посада", "position", "position", default_visible=True)
_add("position_code", "Код штатної посади", "position", "position", "code")
_add("rank", "Звання", "rank", "rank", "nominative", default_visible=True)
_add("rank_order_date", DATE_FIELDS["rank.rank_order_date"].label, "rank", "person_rank", "rank_order_date",
     data_type="partial_date", date_field=DATE_FIELDS["rank.rank_order_date"], prefix="rank_order")
_add("rank_order_number", "Номер наказу про звання", "rank", "person_rank")
_add("rank_code", "Код звання", "rank", "rank", "code")
for case_name, case_label in (("genitive", "родовий"), ("dative", "давальний"), ("accusative", "знахідний"),
                              ("instrumental", "орудний"), ("locative", "місцевий"), ("vocative", "кличний")):
    _add(f"name_{case_name}", f"Посада — {case_label} відмінок", "position", "position")
    _add(f"rank_{case_name}", f"Звання — {case_label} відмінок", "rank", "rank", case_name)
_add("full_name", "ПІБ", "person", "name", "full_name", default_visible=True)
for key, label in (("surname", "Прізвище"), ("name", "Ім'я"), ("patronymic", "По батькові")):
    _add(key, label, "person", "name", default_visible=True)
_add("birth_date", BIRTH_DATE.label, "person", "person", "birth_date", data_type="partial_date",
     date_field=BIRTH_DATE, prefix="birth", default_visible=True)
_add("tax_number", "РНОКПП", "person", "person")
for key, label in (("surname_latin", "Прізвище латиницею"), ("name_latin", "Ім'я латиницею"),
                   ("patronymic_latin", "По батькові латиницею")):
    _add(key, label, "person", "name")
for key, label, attr in (("service_type", "Вид служби", "service_type"), ("military_unit", "Військова частина", "military_unit"),
                         ("service_position", "Посада під час служби", "position"), ("service_order_number", "Номер наказу про службу", "order_number")):
    _add(key, label, "service", "service", attr)
for key, prefix in (("service_position_date", "position"), ("service_order_date", "order")):
    policy = DATE_FIELDS[f"service.{prefix}_date"]
    _add(key, policy.label, "service", "service", f"{prefix}_date", data_type="partial_date", date_field=policy, prefix=prefix)
for key, label in (("passport_type", "Тип паспорта"), ("passport_series", "Серія паспорта"),
                   ("passport_number", "Номер паспорта"), ("passport_issued_by", "Орган видачі паспорта")):
    _add(key, label, "documents", "passport")
for prefix in ("passport_issued", "passport_expire"):
    policy = DATE_FIELDS[f"passport.{prefix}_date"]
    _add(f"{prefix}_date", policy.label, "documents", "passport", f"{prefix}_date",
         data_type="partial_date", date_field=policy, prefix=prefix)
for source, label in (("name", "ПІБ"), ("person_rank", "Звання"), ("passport", "Паспорт"), ("service", "Служба")):
    for attr, suffix, kind in (("created_at", "створено", "datetime"), ("updated_at", "оновлено", "datetime"), ("is_active", "активний запис", "boolean")):
        _add(f"{source}_{attr}", f"{label}: {suffix}", "system_data", source, attr, data_type=kind)

_add("full_address", "Повна адреса реєстрації", "person", "person", "full_address")

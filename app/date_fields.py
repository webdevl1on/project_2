"""Explicit domain policies, independent of ORM and table display metadata."""

from dataclasses import asdict, dataclass
from datetime import date


@dataclass(frozen=True)
class DateField:
    key: str
    label: str
    allow_partial: bool = False
    required: bool = False
    min_year: int = 1
    max_year: int = 9999
    system: bool = False

    def __post_init__(self):
        if not 1 <= self.min_year <= self.max_year <= 9999:
            raise ValueError("Межі років мають належати календарю Python: 1–9999.")
        if self.system and self.allow_partial:
            raise ValueError("Системні часові позначки не можуть бути неповними.")

    def metadata(self):
        return asdict(self)


BIRTH_DATE = DateField("birth_date", "Дата народження", allow_partial=True, max_year=date.today().year)
EVENT_START = DateField("date_start", "Початок події", required=True)
EVENT_END = DateField("date_end", "Кінець події")
EVENT_ORDER = DateField("order_date", "Дата наказу події")
DATE_FIELDS = {
    "person.birth_date": BIRTH_DATE,
    "event.date_start": EVENT_START,
    "event.date_end": EVENT_END,
    "event.order_date": EVENT_ORDER,
    **{key: DateField(key.rsplit(".", 1)[-1], label, allow_partial=True) for key, label in (
        ("passport.passport_issued_date", "Дата видачі паспорта"),
        ("passport.passport_expire_date", "Закінчення дії паспорта"),
        ("rank.rank_order_date", "Дата наказу про звання"),
        ("service.position_date", "Дата посади"),
        ("service.order_date", "Дата наказу про службу"),
        ("service.end_date", "Завершення історичної служби"),
    )},
    "history.created_at": DateField("created_at", "Створено", required=True, system=True),
    "history.updated_at": DateField("updated_at", "Оновлено", required=True, system=True),
}

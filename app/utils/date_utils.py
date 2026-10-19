from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, UTC


@dataclass(frozen=True)
class DateComponents:
    day: int | None
    month: int | None
    year: int | None

    def as_dict(self, prefix="birth") -> dict[str, int | None]:
        return {
            f"{prefix}_day": self.day,
            f"{prefix}_month": self.month,
            f"{prefix}_year": self.year,
        }

    def as_date(self) -> date | None:
        """Return an exact date only when every component is known."""
        if None in (self.day, self.month, self.year):
            return None
        return date(self.year, self.month, self.day)


def _parse_component(value, field_name: str) -> int | None:
    if value is None or str(value).strip() == "":
        return None

    text = str(value).strip()
    if not text.isdecimal():
        raise ValueError(f"{field_name} має містити лише цифри.")
    return int(text)


def validate_date_components(
    day=None,
    month=None,
    year=None,
    *,
    full: bool = False,
    min_year: int = 1,
    max_year: int | None = None,
) -> DateComponents:
    day = _parse_component(day, "День")
    month = _parse_component(month, "Місяць")
    year = _parse_component(year, "Рік")

    if full and None in (day, month, year):
        raise ValueError("Для повної дати потрібно вказати день, місяць і рік.")

    if day is not None and not 1 <= day <= 31:
        raise ValueError("День має бути від 1 до 31.")
    if month is not None and not 1 <= month <= 12:
        raise ValueError("Місяць має бути від 1 до 12.")
    max_year = date.today().year if max_year is None else min(max_year, 9999)
    if year is not None and not max(1, min_year) <= year <= max_year:
        raise ValueError("Рік має бути в допустимому діапазоні.")

    if day is not None and month is not None:
        if year is not None:
            try:
                date(year, month, day)
            except ValueError as error:
                raise ValueError("Такої календарної дати не існує.") from error
        elif day > monthrange(2000 if month == 2 else 2001, month)[1]:
            raise ValueError("День не відповідає обраному місяцю.")

    return DateComponents(day=day, month=month, year=year)


def format_partial_date(day=None, month=None, year=None) -> str:
    components = validate_date_components(day, month, year, max_year=9999)
    return ".".join("_" if value is None else f"{value:0{width}d}" for value, width in (
        (components.day, 2), (components.month, 2), (components.year, 4),
    ))


def validate_field_date(field, day=None, month=None, year=None):
    if field.system:
        raise ValueError("Системні часові позначки не редагуються через поля дат.")
    components = validate_date_components(day, month, year, min_year=field.min_year, max_year=field.max_year)
    values = (components.day, components.month, components.year)
    if (field.required or (not field.allow_partial and any(value is not None for value in values))) and None in values:
        raise ValueError("Потрібна точна дата: день, місяць і рік.")
    return components


def parse_exact_date(value, *, required=False):
    if value is None or value == "":
        if required:
            raise ValueError("Потрібна точна дата: день, місяць і рік.")
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return datetime.strptime(value, "%d.%m.%Y").date()
    except (TypeError, ValueError) as error:
        raise ValueError("Потрібна точна календарна дата ДД.ММ.РРРР.") from error


def date_values_from_input(field, prefix, data, *, current=None):
    """Read explicit components, retaining omitted values during an update.

    The legacy *_date input accepts an exact date or None, never placeholders.
    Mixing it with component inputs is rejected instead of guessing precedence.
    """
    keys = [f"{prefix}_{part}" for part in ("day", "month", "year")]
    legacy_key = f"{prefix}_date"
    if any(key in data for key in keys):
        if data.get(legacy_key) not in (None, ""):
            raise ValueError("Передайте або складові дати, або точну дату, не обидва формати.")
        values = [data[key] if key in data else getattr(current, key, None) for key in keys]
    elif legacy_key in data:
        exact = parse_exact_date(data[legacy_key])
        values = [exact.day, exact.month, exact.year] if exact else [None, None, None]
    else:
        values = [getattr(current, key, None) for key in keys]
    return validate_field_date(field, *values).as_dict(prefix)


def format_system_timestamp(value):
    if value is None:
        return "—"
    if not isinstance(value, datetime):
        raise ValueError("Системна часова позначка має містити дату й час.")
    # SQLite returns naive values; existing HistoryModel defaults mean UTC.
    value = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return value.strftime("%d.%m.%Y %H:%M:%S.%f UTC")


def register_date_globals(environment):
    environment.globals.update(format_partial_date=format_partial_date, format_system_timestamp=format_system_timestamp)

from calendar import monthrange
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DateComponents:
    day: int | None
    month: int | None
    year: int | None

    def as_dict(self) -> dict[str, int | None]:
        return {
            "birth_day": self.day,
            "birth_month": self.month,
            "birth_year": self.year,
        }


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
    if year is not None and not 1 <= year <= date.today().year:
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
    components = validate_date_components(day, month, year)
    parts = []

    if components.day is not None:
        parts.append(f"{components.day:02d}")
    if components.month is not None:
        parts.append(f"{components.month:02d}")
    if components.year is not None:
        parts.append(f"{components.year:04d}")

    if components.day is not None and components.month is None and components.year is None:
        return f"{components.day:02d}."
    if components.day is None and components.month is not None and components.year is None:
        return f".{components.month:02d}."
    if components.day is not None and components.month is None and components.year is not None:
        return f"{components.day:02d}._.{components.year:04d}"

    result = ".".join(parts)
    if components.day is not None and components.month is not None and components.year is None:
        result += "."
    return result

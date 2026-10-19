"""Model-independent date predicates and explicit SQLAlchemy column bindings.

SQLite's deterministic scalar function evaluates calendar possibility without
inventing stored values. Registration is connection-local, not a schema change.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
import json

from sqlalchemy import Integer, case, cast, extract, func

from app.date_fields import DateField
from app.utils.date_utils import validate_date_components


DEFAULT_PRIORITY = ("year", "month", "day")


def date_priority(value=None):
    parts = tuple(value.split(",")) if isinstance(value, str) else tuple(value or DEFAULT_PRIORITY)
    if len(parts) != 3 or set(parts) != set(DEFAULT_PRIORITY):
        raise ValueError("Пріоритет дати має містити рік, місяць і день рівно по одному разу.")
    return parts


def _selections(values, lower, upper):
    if not isinstance(values, list) or any(type(value) is not int or not lower <= value <= upper for value in values):
        raise ValueError("Некоректний вибір компонентів дати.")
    return tuple(sorted(set(values)))


@dataclass(frozen=True)
class DateFilter:
    mode: str = "parts"
    years: tuple[int, ...] = ()
    months: tuple[int, ...] = ()
    days: tuple[int, ...] = ()
    start: date | None = None
    end: date | None = None
    incomplete_only: bool = False

    @classmethod
    def from_json(cls, value):
        try:
            data = json.loads(value) if isinstance(value, str) else value
            if not isinstance(data, dict) or data.get("mode", "parts") not in ("parts", "range"):
                raise ValueError()
            if type(data.get("incomplete_only", False)) is not bool:
                raise ValueError()
            years = _selections(data.get("years", []), 1, 9999)
            months = _selections(data.get("months", []), 1, 12)
            days = _selections(data.get("days", []), 1, 31)
            boundaries = []
            for key in ("start", "end"):
                raw = data.get(key)
                if raw and (not isinstance(raw, str) or len(raw) != 10):
                    raise ValueError()
                boundaries.append(date.fromisoformat(raw) if raw else None)
            start, end = boundaries
            if start and end and start > end:
                raise ValueError()
            mode = data.get("mode", "parts")
            return cls(mode, years if mode == "parts" else (), months if mode == "parts" else (),
                       days if mode == "parts" else (), start if mode == "range" else None,
                       end if mode == "range" else None, data.get("incomplete_only", False))
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError("Некоректний фільтр дати або межі діапазону.") from error

    @property
    def active(self):
        return bool(self.years or self.months or self.days or self.start or self.end or self.incomplete_only)

    def as_dict(self):
        return {"mode": self.mode, "years": list(self.years), "months": list(self.months),
                "days": list(self.days), "start": self.start.isoformat() if self.start else None,
                "end": self.end.isoformat() if self.end else None, "incomplete_only": self.incomplete_only}

    def to_json(self):
        return json.dumps(self.as_dict(), separators=(",", ":"), sort_keys=True)


def possible_match(day, month, year, spec: DateFilter, field: DateField):
    if field.system:
        raise ValueError("Системні часові позначки не є неповними предметними датами.")
    try:
        components = validate_date_components(day, month, year, min_year=field.min_year, max_year=field.max_year)
    except ValueError:
        return False
    day, month, year = components.day, components.month, components.year
    incomplete = None in (day, month, year)
    if (not field.allow_partial and incomplete) or (spec.incomplete_only and not incomplete):
        return False
    lower = max(spec.start or date.min, date(field.min_year, 1, 1))
    upper = min(spec.end or date.max, date(field.max_year, 12, 31))
    if lower > upper:
        return False
    years = (year,) if year is not None else (spec.years or range(lower.year, upper.year + 1))
    months = (month,) if month is not None else (spec.months or range(1, 13))
    days = (day,) if day is not None else (spec.days or range(1, 32))
    for candidate_year in years:
        if not lower.year <= candidate_year <= upper.year or (spec.years and candidate_year not in spec.years):
            continue
        for candidate_month in months:
            if spec.months and candidate_month not in spec.months:
                continue
            for candidate_day in days:
                if (spec.days and candidate_day not in spec.days) or candidate_day > monthrange(candidate_year, candidate_month)[1]:
                    continue
                if lower <= date(candidate_year, candidate_month, candidate_day) <= upper:
                    return True
    return False


def date_sort_key(day, month, year, priority=DEFAULT_PRIORITY, direction="asc"):
    values = {"day": day, "month": month, "year": year}
    missing = sum(value is None for value in values.values())
    category = 0 if not missing else (2 if missing == 3 else 1)
    result = [category]
    for key in date_priority(priority):
        value = values[key]
        result.extend((value is None, (-value if direction == "desc" else value) if value is not None else 0))
    return tuple(result)


@lru_cache(maxsize=128)
def _cached_spec(encoded):
    return DateFilter.from_json(encoded)


def _sqlite_match(day, month, year, encoded, allow_partial, min_year, max_year):
    field = DateField("query", "", allow_partial=bool(allow_partial), min_year=min_year, max_year=max_year)
    return int(possible_match(day, month, year, _cached_spec(encoded), field))


@dataclass(frozen=True)
class DateBinding:
    field: DateField
    day: object
    month: object
    year: object

    def __post_init__(self):
        if self.field.system:
            raise ValueError("Для системного DateTime потрібне точне сортування, без partial-date binding.")

    @classmethod
    def exact(cls, field, column):
        if field.allow_partial:
            raise ValueError("Один SQL Date не зберігає незалежно невідомі компоненти.")
        return cls(field, *(cast(extract(part, column), Integer) for part in ("day", "month", "year")))

    def filter(self, query, spec):
        connection = query.session.connection()
        if connection.dialect.name != "sqlite":
            raise ValueError("Для іншої СУБД потрібно підключити її date-query adapter.")
        connection.connection.driver_connection.create_function("project2_date_match", 7, _sqlite_match, deterministic=True)
        return query.filter(func.project2_date_match(self.day, self.month, self.year, spec.to_json(),
                            self.field.allow_partial, self.field.min_year, self.field.max_year) == 1)

    def order_by(self, priority=DEFAULT_PRIORITY, direction="asc"):
        columns = {"day": self.day, "month": self.month, "year": self.year}
        missing = [column.is_(None) for column in columns.values()]
        result = [case((~missing[0] & ~missing[1] & ~missing[2], 0),
                       (missing[0] & missing[1] & missing[2], 2), else_=1).asc()]
        for part in date_priority(priority):
            column = columns[part]
            result.extend((column.is_(None).asc(), column.desc() if direction == "desc" else column.asc()))
        return result

"""Canonical date components with compatible, derived SQL Date projections."""

from sqlalchemy import event
from sqlalchemy.ext.hybrid import hybrid_property

from app.utils.date_utils import date_values_from_input, validate_field_date


class PartialDateMixin:
    __date_fields__ = {}

    def date_components(self, prefix):
        field = self.__date_fields__[prefix]
        return validate_field_date(field, *(getattr(self, f"{prefix}_{part}") for part in ("day", "month", "year")))

    @classmethod
    def date_binding(cls, prefix):
        from app.utils.date_query import DateBinding
        return DateBinding(cls.__date_fields__[prefix], *(getattr(cls, f"{prefix}_{part}") for part in ("day", "month", "year")))

    @classmethod
    def __declare_last__(cls):
        for name in ("before_insert", "before_update"):
            if not event.contains(cls, name, _validate_and_project):
                event.listen(cls, name, _validate_and_project)


def _validate_and_project(mapper, connection, target):
    for prefix in target.__date_fields__:
        components = target.date_components(prefix)
        for key, value in components.as_dict(prefix).items():
            setattr(target, key, value)
        setattr(target, f"_{prefix}_date", components.as_date())


def date_projection(prefix):
    """Legacy instance writes split into components; SQL reads use a projection.

    Partial-date predicates must use date_binding(), not this nullable Date.
    """
    @hybrid_property
    def value(self):
        return self.date_components(prefix).as_date()

    @value.setter
    def value(self, exact):
        values = date_values_from_input(self.__date_fields__[prefix], prefix, {f"{prefix}_date": exact})
        for key, part in values.items():
            setattr(self, key, part)

    @value.expression
    def value(cls):
        return getattr(cls, f"_{prefix}_date")

    return value

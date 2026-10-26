"""Compatibility passport factory; persistence belongs to the caller."""
from app.models.person_identity import Passport


class CommonPersonFunc:
    @staticmethod
    def add_pasport(
        person_id,
        passport_series,
        passport_number,
        passport_issued_by,
        passport_issued_date=None,
        passport_expire_date=None,
        **date_components,
    ):
        from app.date_fields import DATE_FIELDS
        from app.utils.date_utils import date_values_from_input

        dates = {}
        for prefix, exact in (("passport_issued", passport_issued_date), ("passport_expire", passport_expire_date)):
            source = dict(date_components)
            if exact is not None or not any(f"{prefix}_{part}" in source for part in ("day", "month", "year")):
                source[f"{prefix}_date"] = exact
            dates.update(date_values_from_input(DATE_FIELDS[f"passport.{prefix}_date"], prefix, source))
        return Passport(
            person_id=person_id,
            passport_series = passport_series,
            passport_number = passport_number,
            passport_issued_by = passport_issued_by,
            **dates,
        )

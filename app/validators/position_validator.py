class PositionValidator:

    @staticmethod
    def validate_position_number(num: str | int | None) -> int:
        if num is None or not str(num).strip():
            raise ValueError("Position number cannot be empty")

        try:
            num = int(num)
        except (ValueError, TypeError):
            raise ValueError("Position number must be an integer")

        if num <= 0:
            raise ValueError("Position number must be greater than 0")

        return num

    @staticmethod
    def validate_required_text(value):
        value = value.strip().lower() if value else ""

        if not value:
            raise ValueError("Field cannot be empty")

        return value

    @staticmethod
    def validate_optional_text(value):
        value = value.strip().lower() if value else None

        return value

POSITION_ATTRIBUTES = ("position_number", "code", "unit_short", "name_short", "name_nominative",
                       "name_genitive", "name_dative", "name_accusative", "name_instrumental",
                       "name_locative", "name_vocative")


def validate_position(row):
    """The existing worksheet and historical-position correction share rules."""
    result = {"position_number": PositionValidator.validate_position_number(row["position_number"])}
    for key in POSITION_ATTRIBUTES[1:]:
        result[key] = PositionValidator.validate_required_text(str(row.get(key) or ""))
    result["code"] = result["code"].upper()
    return result

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
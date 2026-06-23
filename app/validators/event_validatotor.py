from datetime import datetime, date

class EventValidator:
    
    @staticmethod
    def validate_event_name(name):
        name = name.strip() if name else None
        if not name:
            raise ValueError("Event name cannot be empty.")
        if len(name) > 255:
            raise ValueError("Event name cannot exceed 255 characters.")
        return name
    
    @staticmethod
    def validate_event_date(event_date: str | None) -> date | None:
        if not event_date:
            return None 
        try:
            return datetime.strptime(
                event_date,
                "%d.%m.%Y"
            ).date()
        except ValueError:
            raise ValueError(
                "Invalid date format. Use DD.MM.YYYY"
            )
       
    @staticmethod
    def validate_event_duration(event_duration)->int | None:
        if event_duration is None or event_duration=="":
            return None 
                
        try:
            duration = int(event_duration)
            if duration <= 0:
                raise ValueError("Event duration cannot be negative.")  
            return duration 
        except ValueError:

            raise ValueError(
                "Invalid event duration. Use days"
            )

    @staticmethod
    def validate_event_location(location):
        location = location.strip() if location else None
        if location and len(location) > 255:
            raise ValueError("Event location cannot exceed 255 characters.")
        return location
    
    @staticmethod
    def validate_event_note(description):
        description = description.strip() if description else None
        if description and len(description) > 1000:
            raise ValueError("Event note cannot exceed 1000 characters.")
        return description
   
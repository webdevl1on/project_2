from datetime import datetime

class PersonValidator:
    
    @staticmethod
    def validate_person_pib(pib):
        pib = pib.strip() if pib else None
        if not pib:
            raise ValueError("PIB cannot be empty.")
        if len(pib) > 255:

            raise ValueError("PIB cannot exceed 255 characters.")
        return pib
   
    @staticmethod
    def validate_person_rank(rank):
        rank = rank.strip() if rank else None
        if rank and len(rank) > 100:
            raise ValueError("Rank cannot exceed 100 characters.")
        return rank.strip() if rank else None
    
    @staticmethod
    def validate_person_phone(phone):
        phone = phone.strip() if phone else None
        if phone and len(phone) > 20:
            raise ValueError("Phone number cannot exceed 20 characters.")
        return phone.strip() if phone else None
   
    @staticmethod
    def validate_person_birth_date(birth_date):
        if not birth_date:
            return None 
        try:
            return datetime.strptime(
                birth_date,
                "%d.%m.%Y"
            ).date()

        except ValueError:

            raise ValueError(
                "Невірний формат дати. Використовуйте ДД.ММ.РРРР"
            )
        
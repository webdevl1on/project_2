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
    def validate_names(name):
        name = name.strip() if name else None
        if name:
            name = name.capitalize()
            if len(name) > 40:
                raise ValueError("Cannot exceed 40 characters.")
            elif len(name) < 2:
                raise ValueError("Canot be so short")
        return name
    @staticmethod
    def validate_tax_number(number):
        number = number.strip() if number else None
        if number:
            if not number.isdecimal():
                raise ValueError('Wrong tax number')
            if len(number) != 10:
                raise ValueError('Wrong tax number')
        return number
   
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
    
    @staticmethod
    def validate_passport_type(passport_type):
        passport_type = passport_type.strip() if passport_type else None
        if passport_type is None:
            raise ValueError("Wrong type of passport")
        if passport_type:
            passport_type = passport_type.lower()
        if passport_type != "id" or passport_type !="book":
            raise ValueError("Wrong type of passport")
        return passport_type
    
    @staticmethod
    def validate_passport_series_id(passport_series):
        passport_series = passport_series.strip() if passport_series else None
        if passport_series is not None:
            raise ValueError ('Wrong ID, must be empty')
        return passport_series
    
    @staticmethod
    def validate_passport_series_book(passport_series):
        passport_series = passport_series.strip() if passport_series else None
        if passport_series is None or len(passport_series) !=2:
            raise ValueError ('Wrong series')
        if not passport_series.isalpha():
            raise ValueError ('Wrong series')
        return passport_series
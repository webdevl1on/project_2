from datetime import datetime

class PersonValidator:
#person name data validation
    @staticmethod
    def validate_names(name):
        name = name.strip() if name else None
        if name:
            name = name.capitalize()
            if not name.isalpha():
                raise ValueError("Wrong letters")
            if len(name) > 25:
                raise ValueError("Cannot exceed 25 characters.")
            elif len(name) < 3:
                raise ValueError("Canot be so short")
        return name
#person base data validation
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
   
#person passport data validation
    @staticmethod
    def validate_passport_type(passport_type):
        passport_type = passport_type.strip().lower() if passport_type else None
        if passport_type not in ("id", "book"):
            raise ValueError("Wrong type of passport")
        return passport_type
    #person passport id card validataion
    @staticmethod
    def validate_passport_series_id(passport_series):
        passport_series = passport_series.strip() if passport_series else None
        if passport_series is not None:
            raise ValueError ('Wrong ID, must be empty')
        return passport_series
    
    @staticmethod
    def validate_passport_number_id(passport_number):
        passport_number = passport_number.strip() if passport_number else None
        if not passport_number or passport_number is None:
            return None
        if not passport_number.isdecimal() or len(passport_number)!=9:
            raise ValueError("Wrong number")
        return passport_number
    
    @staticmethod
    def validate_issued_by_id(passport_issued_by):
        passport_issued_by = passport_issued_by.strip() if passport_issued_by else None
        if passport_issued_by is None:
            return passport_issued_by 
        if not passport_issued_by.isdecimal() or len(passport_issued_by)!=4:
            raise ValueError("Wrong issued")
        return passport_issued_by
    
    #person passport book validataion
    @staticmethod
    def validate_passport_series_book(passport_series):
        passport_series = passport_series.strip().upper() if passport_series else None
        if passport_series is None:
            return None
        if not passport_series.isalpha() or len(passport_series) !=2:
            raise ValueError ('Wrong series')
        return passport_series
    
    @staticmethod
    def validate_issued_by_book(passport_issued_by):
        passport_issued_by = passport_issued_by.strip() if passport_issued_by else None
        if passport_issued_by is None:
            return None 
        if len(passport_issued_by) > 300:
            raise ValueError("Wrong issued")
        return passport_issued_by











#person fullname data validation        
    @staticmethod
    def validate_person_pib(pib):
        pib = pib.strip() if pib else None
        if not pib:
            raise ValueError("PIB cannot be empty.")
        if len(pib) > 255:

            raise ValueError("PIB cannot exceed 255 characters.")
        return pib
    
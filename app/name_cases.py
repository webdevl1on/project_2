"""Display metadata shared by forms, dictionaries and the Excel contract."""
CASES = {
    "nominative": "Називний", "genitive": "Родовий", "dative": "Давальний",
    "accusative": "Знахідний", "instrumental": "Орудний", "locative": "Місцевий",
    "vocative": "Кличний",
}
NAME_PARTS = {"surname": "Прізвище", "name": "Ім'я", "patronymic": "По батькові"}
SEXES = {"male": "Чоловіча", "female": "Жіноча"}
SHEETS = {"surnames": "surname", "names": "name", "patronymics": "patronymic"}
IMPORT_HEADERS = ("base_form", "sex", *CASES)

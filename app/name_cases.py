"""Display metadata shared by forms, dictionaries and the Excel contract."""
CASES = {
    "nominative": "Називний", "genitive": "Родовий", "dative": "Давальний",
    "accusative": "Знахідний", "instrumental": "Орудний", "locative": "Місцевий",
    "vocative": "Кличний",
}
NAME_PARTS = {"surname": "Прізвище", "name": "Ім'я", "patronymic": "По батькові"}
SEXES = {"male": "Чоловіча", "female": "Жіноча"}
SHEETS = {
    "surname_male": ("surname", "male"),
    "names_male": ("name", "male"),
    "patronimic_male": ("patronymic", "male"),
    "surname_female": ("surname", "female"),
    "names_female": ("name", "female"),
    "patronimic_female": ("patronymic", "female"),
}
EXCEL_HEADERS = ("base_form", *CASES)
EXCEL_LABELS = ("Основна форма", *CASES.values())
# Editor fields retain sex; Excel derives it exclusively from the sheet name.
IMPORT_HEADERS = ("base_form", "sex", *CASES)

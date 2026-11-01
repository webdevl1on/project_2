"""Stable subject codes and presentation metadata for additional profile records."""
from app.geography import GEO_FIELDS
EDUCATION_LEVELS = {
    'general_secondary': 'Загальна середня освіта',
    'vocational': 'Професійна освіта',
    'professional_prehigher': 'Фахова передвища освіта',
    'higher_short': 'Вища освіта — короткий цикл',
    'higher_bachelor': 'Вища освіта — бакалавр',
    'higher_master': 'Вища освіта — магістр',
    'higher_specialist': 'Вища освіта — спеціаліст',
}

KINSHIP = dict(zip(
    ('wife','husband','mother','father','son','daughter','brother','sister','grandfather','grandmother','other'),
    ('Дружина','Чоловік','Мати','Батько','Син','Донька','Брат','Сестра','Дідусь','Бабуся','Інший родич'),
))

# (key, label, control type, choices or maximum length, required)
FIELDS = {
    'education': [
        ('level_code', 'Рівень освіти', 'select', EDUCATION_LEVELS, True),
        ('started_on', 'Дата початку', 'date', None, False),
        ('ended_on', 'Дата закінчення', 'date', None, False),
        ('institution', 'Навчальний заклад', 'text', 500, False),
        ('faculty', 'Факультет', 'text', 500, False),
        ('specialty', 'Спеціальність', 'text', 500, False),
    ],
    'family': [
        ('kinship', 'Ступінь рідства', 'select', KINSHIP, True),
        ('full_name', 'ПІБ', 'text', 500, True),
        ('birth_on', 'Дата народження', 'date', None, False),
        ('death_on', 'Дата смерті', 'date', None, False),
        ('phone', 'Телефон', 'text', 100, False),
        ('address_text', 'Адреса згідно з документом / довільний текст', 'textarea', 2000, False),
        *[(key, label, 'geo', 250, False) for key, label in GEO_FIELDS.items()],
        ('settlement_type', 'Тип населеного пункту', 'text', 60, False),
        ('street', 'Назва вулиці', 'geo', 250, False),
        ('street_type', 'Тип вулиці', 'text', 250, False),
        *[(key, label, 'text', 250, False) for key, label in [('house','Будинок'),('corps','Корпус'),('building','Будівля'),('apartment','Квартира'),('room','Кімната')]],
    ],
    'directives': [
        ('number', 'Номер', 'text', 300, False),
        ('issued_on', 'Дата', 'date', None, False),
    ],
}
LABELS = {'education': 'Освіта', 'family': "Сім'я", 'directives': 'Особисті розпорядження'}

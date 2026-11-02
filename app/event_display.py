"""Shared presentation metadata, never a source of personnel facts."""
STYLES = {
    'SERVICE': ('служба', 'service', 'check'),
    'DUTY': ('чергування', 'service', 'check'),
    'DAY_OFF': ('вихідний', 'other', 'clock'),
    'VACATION': ('відпустка', 'vacation', 'case'),
    'HOSPITAL': ('лік', 'hospital', 'medical'),
    'BUSINESS_TRIP': ('відрядження', 'trip', 'plane'),
    'UNAUTHORIZED_ABSENCE': ('СЗЧ', 'absence', 'alert'),
}


def presentation(code=None, name=None):
    if code == '__vacant__':
        return {'code': code, 'label': 'вакантна', 'name': 'Посада не призначена', 'tone': 'vacant', 'icon': 'person'}
    if code == '__conflict__':
        return {'code': code, 'label': 'Кілька подій', 'name': 'Період містить кілька одночасних подій', 'tone': 'conflict', 'icon': 'alert'}
    if code is None:
        return {'code': None, 'label': 'Немає події', 'name': 'Запису події на цю дату немає', 'tone': 'empty', 'icon': 'dash'}
    label, tone, icon = STYLES.get(code, (name or 'Інше', 'other', 'clock'))
    return {'code': code, 'label': label, 'name': name or label.capitalize(), 'tone': tone, 'icon': icon}


def legend():
    return [presentation(code) for code in ('SERVICE', 'VACATION', 'HOSPITAL', 'BUSINESS_TRIP', 'UNAUTHORIZED_ABSENCE')] + [presentation('__vacant__'), presentation()]

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
    if code == '__pending__':
        return {'code': code, 'label': 'Потребує підтвердження завершення', 'name': 'Завершення не підтверджене діловодом', 'tone': 'conflict', 'icon': 'alert'}
    if code in (None, '__base__'):
        return {'code': '__base__', 'label': 'служба', 'name': 'Служба (розрахункова, не підтверджує фізичну присутність)', 'tone': 'service', 'icon': 'check', 'calculated': True}
    label, tone, icon = STYLES.get(code, (name or 'Інше', 'other', 'clock'))
    return {'code': code, 'label': label, 'name': name or label.capitalize(), 'tone': tone, 'icon': icon}


def legend():
    return [presentation(code) for code in ('SERVICE', 'VACATION', 'HOSPITAL', 'BUSINESS_TRIP', 'UNAUTHORIZED_ABSENCE')] + [presentation('__vacant__'), presentation()]


def event_presentation(record):
    """Dictionary colour wins; subtype tints use validated colours and a safe hex fallback."""
    import hashlib
    import re
    result = presentation(record['type_code'], record['type_name'])
    color = record.get('type_color') or ''
    defaults = {'SERVICE': '#398c46', 'DUTY': '#527a31', 'DAY_OFF': '#77726b', 'VACATION': '#e8bc24',
                'BUSINESS_TRIP': '#277ccc', 'HOSPITAL': '#d86691', 'VLK': '#23a9a2', 'UNAUTHORIZED_ABSENCE': '#da3548'}
    if re.fullmatch(r'#[0-9a-fA-F]{3}', color): color = '#' + ''.join(c*2 for c in color[1:])
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
        color = defaults.get(record['type_code'], '#' + hashlib.sha256(record['type_code'].encode()).hexdigest()[:6])
    channels = [int(color[i:i+2], 16) for i in (1, 3, 5)]
    shade = .32 + (int(hashlib.sha256((record.get('subtype_code') or '').encode()).hexdigest()[:2], 16) % 5)*.045 if record.get('subtype_code') else .22
    shade = record.get('subtype_tint', shade)
    if re.fullmatch(r'(?:#[0-9a-fA-F]{3,8}|[a-zA-Z]{1,30}|(?:rgb|hsl)a?\([0-9.,% /+\-]+\))', record.get('type_color') or ''):
        result.update(accent_color=record['type_color'], mix=round(shade*100))
    result.update(background='#' + ''.join(f'{round(255*(1-shade)+c*shade):02x}' for c in channels),
                  foreground='#172337', subtype=record.get('subtype_name'), mirage=record.get('mirage', False))
    return result

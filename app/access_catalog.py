"""Server-owned extensible ACL catalogue. Client renders this registry, never defines rights."""
CATEGORIES = {
    'basic': 'Базова інформація', 'personal': 'Персональні дані',
    'service': 'Служба та призначення', 'documents': 'Документи',
    'medical': 'Медицина', 'family': 'Сім’я', 'events': 'Події',
    'history': 'Історія змін', 'organization': 'Організаційна структура',
}
SPECIAL = {'organization': {'reorder':'Порядок елементів', 'reparent':'Основне підпорядкування',
                            'bind':'Належність посади', 'import':'Імпорт штатки'},
           'personal': {'create':'Створення особи'}, 'documents': {'override':'Ручний статус реквізитів'}}

def actions(category):
    if category not in CATEGORIES:raise ValueError('Невідома категорія доступу.')
    return {'read':'Читання','edit':'Редагування',**SPECIAL.get(category,{})}

def catalog():return [{'key':key,'label':label,'actions':actions(key)} for key,label in CATEGORIES.items()]

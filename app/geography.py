"""Shared geographic field metadata; no inferred or seeded locations."""
GEO_FIELDS = {"country": "Країна", "region": "Область / регіон", "district": "Район", "community": "Територіальна громада", "settlement": "Населений пункт"}
DETAIL_FIELDS = {"street": "Назва вулиці", "street_type": "Тип вулиці", "house": "Будинок", "corps": "Корпус", "building": "Будівля / споруда", "apartment": "Квартира", "room": "Кімната", "postal_code": "Поштовий індекс", "note": "Уточнення"}
ADDRESS_TYPES = {"registration": "Місце реєстрації", "actual": "Фактичне проживання", "correspondence": "Адреса листування"}


def normalize(value):
    import unicodedata
    return ' '.join(unicodedata.normalize('NFC', value or '').casefold().split())

# Full text is stored; abbreviations are display metadata only.
SETTLEMENT_TYPES = {'місто':'м.', 'село':'с.', 'селище':'с-ще', 'селище міського типу':'смт', 'хутір':'х.'}
STREET_TYPES = {'вулиця':'вул.', 'проспект':'просп.', 'провулок':'пров.', 'бульвар':'бульв.', 'площа':'пл.', 'проїзд':'пр-д', 'узвіз':'узвіз', 'набережна':'наб.', 'шосе':'шосе', 'алея':'алея', 'тупик':'туп.'}
SETTLEMENT_TYPE_ALIASES = {'city':'місто', 'special_city':'місто', 'village':'село', 'settlement':'селище'}

BIRTH_COMPONENTS = tuple(GEO_FIELDS)
ADDRESS_COMPONENTS = (*BIRTH_COMPONENTS, 'street', 'house', 'corps', 'building', 'apartment', 'room', 'postal_code')
EMPTY_GEO_MESSAGES = {
    'birthplace': 'Неможливо зберегти порожнє місце народження. Заповніть хоча б один компонент місця народження',
    'address': 'Неможливо зберегти порожню адресу. Заповніть хоча б один компонент адреси',
}

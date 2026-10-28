"""Advisory TCC directory validation; text snapshots are never updated here."""
from sqlalchemy.exc import SQLAlchemyError
from app.database.transactions import service_transaction
from app.models.service_basis import TccOffice
from app.repositories.service_basis_repository import TccRepository as Repo
from app.services.service_bases import text_value, checked, reference_id
from app.utils.text_search import normalized_text

TYPES = {'regional': 'Обласний', 'city': 'Міський', 'district': 'Районний',
         'united_district': "Об’єднаний районний", 'department': 'Відділ'}


def values(data):
    result = {field: text_value(data, field, maximum) for field, maximum in
              [('official_name', 500), ('region', 250), ('settlement', 250)]}
    if not result['official_name']:
        raise ValueError('Вкажіть офіційну назву ТЦК та СП.')
    if data.get('type') not in TYPES:
        raise ValueError('Оберіть тип ТЦК зі списку: ' + ', '.join(TYPES))
    result.update(type=data['type'], is_active=checked(data.get('is_active')),
                  parent_tcc_id=reference_id(data.get('parent_tcc_id'), 'Батьківський ТЦК'))
    result.update(normalized_name=normalized_text(result['official_name']),
                  normalized_region=normalized_text(result['region']), normalized_settlement=normalized_text(result['settlement']))
    return result


def validate_parent(db, parent_id, key=None, proposed=None):
    seen = {key} if key else set()
    while parent_id is not None:
        if parent_id in seen:
            raise ValueError('Циклічний зв’язок батьківських ТЦК заборонений.')
        seen.add(parent_id)
        parent = Repo.get(db, parent_id)
        if parent is None:
            raise ValueError(f'Батьківський ТЦК id={parent_id} не існує. Спочатку додайте його окремо.')
        parent_id = proposed[parent_id] if proposed and parent_id in proposed else parent.parent_tcc_id


def save(db, data, key=None):
    if key is not None:
        key = reference_id(key, 'ТЦК')
    try:
        with service_transaction(db, immediate=True):
            record = Repo.get(db, key) if key else None
            if key and (record is None or str(record.revision) != str(data.get('revision'))):
                raise ValueError('Установу змінено після відкриття форми. Оновіть сторінку.')
            prepared = values(data)
            other = Repo.find(db, prepared)
            if other and other.id != key:
                raise ValueError('ТЦК з такою назвою, областю та населеним пунктом уже існує.')
            validate_parent(db, prepared['parent_tcc_id'], key)
            record = record or Repo.add(db, TccOffice())
            for field, value in prepared.items():
                setattr(record, field, value)
            db.flush()
            result = record.id
        return result
    except SQLAlchemyError:
        raise ValueError('Не вдалося зберегти ТЦК. Усі зміни скасовано; повторіть перевірку.') from None


def suggestions(db, q='', region='', settlement=''):
    return [{'id': r.id, 'official_name': r.official_name, 'region': r.region, 'settlement': r.settlement}
            for r in Repo.list(db, q, active_only=True, region=normalized_text(region), settlement=normalized_text(settlement), limit=30)]


def page(db, q='', page=1):
    page = max(1, page)
    return {'offices': Repo.list(db, q, offset=(page-1)*100, limit=101), 'q': q, 'page': page, 'tcc_types': TYPES}


def record(db, key):
    key = reference_id(key, 'ТЦК')
    row = Repo.get(db, key)
    if row is None:
        raise ValueError('ТЦК не знайдено.')
    return row


def locations(db):
    return {field: Repo.locations(db, getattr(TccOffice, field)) for field in ('region', 'settlement')}

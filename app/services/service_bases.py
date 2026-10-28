"""Explicit service bases; no inference from assignments or legacy text."""
from datetime import date
from sqlalchemy.exc import SQLAlchemyError
from app.database.transactions import service_transaction
from app.models.service_basis import PersonServiceBasis
from app.repositories.service_basis_repository import ServiceBasisRepository as Repo, TccRepository
from app.services.service_person_checking import ServicePersonCheck
from app.service_basis import SERVICE_BASES
from app.utils.text_search import normalized_text as normalize_text


def text_value(data, field, maximum):
    value = data.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f'{field}: потрібне текстове значення.')
    value = value.strip()
    if len(value) > maximum or any(ord(char) < 32 for char in value):
        raise ValueError(f'{field}: максимум {maximum} символів, без керівних символів.')
    return value or None


def optional_date(value, label):
    if value is None or value == '':
        return None
    if type(value) is date:
        return value
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError()
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError()
        return result
    except ValueError:
        raise ValueError(f'{label}: потрібна повна календарна дата або порожнє поле.') from None


def checked(value):
    return value in ('on', '1', 'true', True)


def reference_id(value, label):
    if value is None or value == '':
        return None
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit() or not 1 <= int(value) <= 9223372036854775807:
        raise ValueError(f'{label}: потрібне додатне ціле ID або порожнє поле.')
    return int(value)


def match_status(office, values):
    if office is None:
        return 'unknown'
    pairs = [('document_tcc_name', 'official_name'), ('region', 'region'), ('settlement', 'settlement')]
    if not values.get('document_tcc_name'):
        return 'mismatch'
    return 'matched' if all(not values.get(a) or normalize_text(values[a]) == normalize_text(getattr(office, b) or '') for a, b in pairs) else 'mismatch'


def save(db, person_id, data, key=None):
    if key is not None:
        key = reference_id(key, 'Підстава служби')
    try:
        with service_transaction(db, immediate=True):
            ServicePersonCheck.get_person_or_raise(person_id, db)
            old = Repo.get(db, person_id, key) if key else None
            if key and (old is None or str(old.revision) != str(data.get('revision'))):
                raise ValueError('Підставу вже змінено або не знайдено. Оновіть анкету.')
            kind = data.get('service_type')
            if kind not in SERVICE_BASES:
                raise ValueError('Оберіть вид служби.')
            values = dict(service_type=kind, is_current=checked(data.get('is_current')),
                          document_verified=checked(data.get('document_verified')),
                          mobilization_date=None, region=None, settlement=None, document_tcc_name=None,
                          tcc_office_id=None, match_status='unknown', contract_signed_date=None,
                          contract_start_date=None, enlistment_order_date=None, enlistment_order_number=None, contract_unit=None)
            if kind == 'mobilization':
                values.update({f: text_value(data, f, maximum) for f, maximum in [('region', 250), ('settlement', 250), ('document_tcc_name', 500)]})
                values['mobilization_date'] = optional_date(data.get('mobilization_date'), 'Дата мобілізації')
                office = None
                if data.get('tcc_office_id'):
                    office = TccRepository.get(db, reference_id(data['tcc_office_id'], 'ТЦК'))
                    if office is None:
                        raise ValueError('Установу довідника не знайдено. Приберіть посилання або виберіть іншу; текст документа можна зберегти без довідника.')
                    values['tcc_office_id'] = office.id
                values['match_status'] = match_status(office, values)
            else:
                for field, label in [('contract_signed_date', 'Дата підписання'), ('contract_start_date', 'Дата початку служби'), ('enlistment_order_date', 'Дата наказу')]:
                    values[field] = optional_date(data.get(field), label)
                values['enlistment_order_number'] = text_value(data, 'enlistment_order_number', 100)
                values['contract_unit'] = text_value(data, 'contract_unit', 250)
            if values['is_current']:
                for record in Repo.records(db, person_id):
                    if record.is_current and (old is None or record.id != old.id):
                        record.is_current = False
                db.flush()
            record = old or Repo.add(db, PersonServiceBasis(person_id=person_id))
            for field, value in values.items():
                setattr(record, field, value)
            db.flush()
            result = record.id
        return result
    except SQLAlchemyError:
        raise ValueError('Не вдалося зберегти підставу служби: конфлікт змін. Усі зміни скасовано.') from None


def page(db, person_id):
    records = Repo.records(db, person_id)
    current = next((record for record in records if record.is_current), None)
    return {'service_bases': records, 'current_service_basis': current, 'service_basis_types': SERVICE_BASES,
            'basis_tcc_offices': TccRepository.by_ids(db, {record.tcc_office_id for record in records if record.tcc_office_id}),
            'service_wording': SERVICE_BASES.get(current.service_type) if current else None}

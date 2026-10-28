"""Transactional domain operations; effective dates, never creation order."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from app.repositories.staff_repository import StaffRepository, active
from app.repositories.person_repository import PersonRepository
from app.validators.position_validator import POSITION_ATTRIBUTES, validate_position
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from app.models.staff import StaffStructure, StaffVersion, PersonAssignment, exact_date
from app.models.reference_book import Position
from app.models.person import Person


def today():
    return datetime.now(ZoneInfo("Europe/Kyiv")).date()


def assignments_at(db, on):
    """Compatibility query entry point; SQL construction lives in the repository."""
    return StaffRepository.assignments_at(db, on)


@contextmanager
def write_unit(db):
    # Services own the transaction, as the existing application does. Never
    # discard pending caller writes when restarting a read-only session.
    if db.new or db.dirty or db.deleted:
        raise ValueError("Спочатку завершіть поточні незбережені зміни.")
    db.rollback()
    try:
        if db.bind.dialect.name == "sqlite":
            db.connection().exec_driver_sql("BEGIN IMMEDIATE")
        yield
        db.commit()
    except (IntegrityError, OperationalError, StaleDataError) as error:
        db.rollback()
        message = str(getattr(error, "orig", error))
        if "overlap" in message:
            raise ValueError("Періоди перетинаються: перевірте історію та зайнятість.") from error
        if "outside version" in message:
            raise ValueError("Призначення виходить за період версії штату.") from error
        raise ValueError("Конфлікт або блокування БД. Оновіть дані й повторіть операцію.") from error
    except Exception:
        db.rollback()
        raise


def period(start, end):
    exact_date(start); exact_date(end, False)
    if end is not None and end < start:
        raise ValueError("Завершення не може передувати початку.")


def version_conflict(db, structure_id, start, end, exclude=None):
    period(start, end)
    if StaffRepository.overlapping_version(db, structure_id, start, end or date.max, exclude):
        raise ValueError("Період конфліктує з іншою версією. Явно закрийте попередню версію перед імпортом.")


def checked(db, model, key, revision=None):
    record = PersonRepository.get_by_id(db, key) if model is Person else StaffRepository.get(db, model, key)
    if record is None:
        raise ValueError("Запис не існує.")
    if revision is not None and record.revision != revision:
        raise ValueError("Запис змінився. Оновіть дані й підтвердьте актуальний стан.")
    return record


def order_values(number=None, issued=None, prefix='assignment'):
    number=(number or '').strip()
    if len(number)>100: raise ValueError('Номер наказу: максимум 100 символів.')
    exact_date(issued,False)
    return {prefix+'_order_number':number or None,prefix+'_order_date':issued}


_ORDER_UNSET = object()

class StaffService:
    @staticmethod
    def create_structure(db, code, name):
        if not code.strip() or not name.strip():
            raise ValueError('Вкажіть код і назву структури.')
        with write_unit(db):
            record = StaffRepository.add(db, StaffStructure(code=code.strip(), name=name.strip()))
            db.flush()
            key = record.id
        return key

    @staticmethod
    def create_assignment(db, person_id, position_id, start, end=None, *, order_number=None, order_date=None):
        period(start, end)
        with write_unit(db):
            checked(db, Person, person_id); checked(db, Position, position_id)
            record = PersonAssignment(person_id=person_id, staff_position_id=position_id, assigned_from=start, assigned_to=end, **order_values(order_number,order_date))
            StaffRepository.add(db, record); db.flush()
            key = record.id
        return key

    @staticmethod
    def correct_assignment(db, key, revision, person_id, position_id, start, end):
        period(start, end)
        with write_unit(db):
            record = checked(db, PersonAssignment, key, revision)
            checked(db, Person, person_id); checked(db, Position, position_id)
            record.person_id=person_id; record.staff_position_id=position_id
            record.assigned_from=start; record.assigned_to=end
            db.flush()
        return key

    @staticmethod
    def correct_position(db, key, revision, values):
        with write_unit(db):
            record=checked(db, Position, key, revision)
            current={name: getattr(record,name) for name in POSITION_ATTRIBUTES}
            if set(values) - set(current):
                raise ValueError("Можна виправити лише реквізити конкретної посади, без зміни версії.")
            current.update(values)
            for name,value in validate_position(current).items():
                setattr(record,name,value)
            db.flush()
        return key

    @staticmethod
    def close_version(db, key, revision, end):
        exact_date(end)
        with write_unit(db):
            version=checked(db, StaffVersion, key, revision)
            period(version.valid_from,end)
            if version.valid_to is not None and end > version.valid_to:
                raise ValueError("Закриття не подовжує період; для виправлення використайте редагування версії.")
            records=StaffRepository.assignments_for_version(db, key)
            if any(record.assigned_from>end for record in records):
                raise ValueError("Є призначення після обраного завершення. Спочатку виправте їхні періоди.")
            for record in records:
                if record.assigned_to is None or record.assigned_to>end:
                    record.assigned_to=end
                    record.completion_reason="version_closed"
            db.flush()  # version guard must see already-closed assignment periods
            version.valid_to=end
            db.flush()

    @staticmethod
    def correct_version(db, key, revision, name, start, end):
        period(start,end)
        with write_unit(db):
            record=checked(db,StaffVersion,key,revision)
            version_conflict(db,record.staff_structure_id,start,end,key)
            if not name.strip(): raise ValueError("Вкажіть назву версії.")
            record.name=name.strip();record.valid_from=start;record.valid_to=end
            db.flush()  # refuses periods invalidating any assignment

    @staticmethod
    def assignment_snapshot(db, position_id, person_id, on, orders=None):
        exact_date(on)
        target=checked(db,Position,position_id)
        version=checked(db,StaffVersion,target.staff_version_id)
        if on<version.valid_from or (version.valid_to and on>version.valid_to):
            raise ValueError("Обрана дата не належить періоду цієї версії.")
        source=StaffRepository.person_assignment_at(db, person_id, on) if person_id else None
        occupied=StaffRepository.position_assignment_at(db, position_id, on)
        if person_id: checked(db,Person,person_id)
        if occupied and occupied.person_id!=person_id and person_id is not None:
            raise ValueError("Цільова посада зайнята. Її не буде звільнено автоматично.")
        closing = source if source and source.staff_position_id != position_id else occupied if person_id is None else None
        if closing is not None and closing.assigned_from >= on:
            raise ValueError("Призначення починається обраного дня. Для помилки скористайтеся виправленням історії.")
        def stamp(record): return [record.id,record.revision,record.assigned_from.isoformat(),record.assigned_to.isoformat() if record.assigned_to else None,record.person_id,record.staff_position_id] if record else None
        result = {"position_id":position_id,"person_id":person_id,"on":on.isoformat(),
                "source":stamp(source),"target":stamp(occupied),"version":[version.id,version.revision,version.valid_from.isoformat(),version.valid_to.isoformat() if version.valid_to else None],
                "position_revision":target.revision}
        if orders: result["orders"] = orders
        return result

    @staticmethod
    def assign(db, position_id, person_id, on, expected, confirmed=False):
        with write_unit(db):
            return StaffService._assign_locked(db,position_id,person_id,on,expected,confirmed)

    @staticmethod
    def _assign_locked(db, position_id, person_id, on, expected, confirmed=False):
        snapshot=StaffService.assignment_snapshot(db,position_id,person_id,on,expected.get("orders"))
        if snapshot!=expected:
            raise ValueError("Призначення змінилося. Оновіть форму та повторіть підтвердження.")
        if snapshot["source"] and snapshot["target"]==snapshot["source"]:
            return "Військовослужбовець уже призначений на цю посаду."
        old_id=(snapshot["source"] or snapshot["target"] or [None])[0]
        old=StaffRepository.get(db, PersonAssignment, old_id) if old_id else None
        if old:
            if not confirmed:
                raise ValueError("Перепризначення потребує підтвердження.")
            if old.assigned_from>=on:
                raise ValueError("Призначення починається цього дня. Виправте помилковий запис через редагування історії.")
            old.assigned_to=on-timedelta(days=1)
            old.completion_reason="transfer" if person_id else "release"
            orders=expected.get('orders') or {}
            for key,value in order_values(orders.get('release_number'),date.fromisoformat(orders['release_date']) if orders.get('release_date') else None,'release').items():
                setattr(old,key,value)
            db.flush()
        if person_id is not None:
            position=checked(db,Position,position_id)
            version=checked(db,StaffVersion,position.staff_version_id)
            StaffRepository.add(db, PersonAssignment(person_id=person_id,staff_position_id=position_id,
                                    assigned_from=on,assigned_to=version.valid_to, **order_values((expected.get("orders") or {}).get("number"),date.fromisoformat(expected["orders"]["date"]) if (expected.get("orders") or {}).get("date") else None)))
            db.flush()
        return "Призначення збережено; історію попередньої посади збережено." if person_id else "Призначення завершено."

    @staticmethod
    def correct_orders(db, key, revision, assignment_number=_ORDER_UNSET, assignment_date=_ORDER_UNSET, release_number=_ORDER_UNSET, release_date=_ORDER_UNSET):
        values={}
        for prefix,number,issued in [('assignment',assignment_number,assignment_date),('release',release_number,release_date)]:
            if number is not _ORDER_UNSET:values[prefix+'_order_number']=order_values(number,None,prefix)[prefix+'_order_number']
            if issued is not _ORDER_UNSET:
                exact_date(issued,False);values[prefix+'_order_date']=issued
        with write_unit(db):
            record=checked(db,PersonAssignment,key,revision)
            for field,value in values.items():setattr(record,field,value)
            db.flush()
        return key

    @staticmethod
    def release_assignment(db,key,revision,effective,number=None,issued=None,note=None,confirmed=False):
        exact_date(effective)
        if not confirmed:raise ValueError('Підтвердьте звільнення саме з посади.')
        values=order_values(number,issued,'release')
        if len(note or '')>1000:raise ValueError('Примітка: максимум 1000 символів.')
        with write_unit(db):
            record=checked(db,PersonAssignment,key,revision)
            if effective<=record.assigned_from:raise ValueError('Дата звільнення має бути пізніше першого дня призначення.')
            end=effective-timedelta(days=1)
            if (record.completion_reason and record.assigned_to!=end) or (record.assigned_to is not None and end>record.assigned_to):
                raise ValueError('Призначення вже завершене або дата виходить за його межі. Використайте виправлення історичних дат.')
            record.assigned_to=end;record.completion_reason='release';record.completion_note=(note or '').strip() or None
            for field,value in values.items():setattr(record,field,value)
            db.flush()
        return key


def domain_date(raw, required=True):
    if not raw and not required:return None
    try:return date.fromisoformat(raw)
    except (ValueError,TypeError):raise ValueError('Потрібна точна дата у форматі РРРР-ММ-ДД.') from None

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
    def create_assignment(db, person_id, position_id, start, end=None):
        period(start, end)
        with write_unit(db):
            checked(db, Person, person_id); checked(db, Position, position_id)
            record = PersonAssignment(person_id=person_id, staff_position_id=position_id, assigned_from=start, assigned_to=end)
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
    def assignment_snapshot(db, position_id, person_id, on):
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
        return {"position_id":position_id,"person_id":person_id,"on":on.isoformat(),
                "source":stamp(source),"target":stamp(occupied),"version":[version.id,version.revision,version.valid_from.isoformat(),version.valid_to.isoformat() if version.valid_to else None],
                "position_revision":target.revision}

    @staticmethod
    def assign(db, position_id, person_id, on, expected, confirmed=False):
        with write_unit(db):
            snapshot=StaffService.assignment_snapshot(db,position_id,person_id,on)
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
                db.flush()
            if person_id is not None:
                position=checked(db,Position,position_id)
                version=checked(db,StaffVersion,position.staff_version_id)
                StaffRepository.add(db, PersonAssignment(person_id=person_id,staff_position_id=position_id,
                                        assigned_from=on,assigned_to=version.valid_to))
                db.flush()
        return "Призначення збережено; історію попередньої посади збережено." if person_id else "Призначення завершено."

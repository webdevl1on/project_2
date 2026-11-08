"""Transactional domain operations; effective dates, never creation order."""
from contextlib import contextmanager
from datetime import date, datetime, timedelta, UTC
from zoneinfo import ZoneInfo
from app.repositories.staff_repository import StaffRepository, active
from app.repositories.person_repository import PersonRepository
from app.validators.position_validator import POSITION_ATTRIBUTES, validate_position
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm.exc import StaleDataError
from app.models.staff import StaffStructure, StaffVersion, PersonAssignment, exact_date
from app.models.reference_book import Position
from app.models.person import Person
from app.services.assignment_audit import snapshot as audit_snapshot, record_change


def today():
    return datetime.now(ZoneInfo("Europe/Kyiv")).date()


def official_start(start, previous=None):
    exact_date(start)
    if start != previous and start > today() + timedelta(days=1):
        raise ValueError("Початок офіційного призначення дозволений не пізніше завтра (Europe/Kyiv). Для планування використайте Міраж.")


def editable(record):
    if record.annulled_at is not None:
        raise ValueError("Призначення анульоване. Спочатку відновіть його з перевіркою конфліктів.")


def completion_values(number=None, issued=None, reason=None, note=None):
    if len(note or '') > 1000: raise ValueError('Примітка: максимум 1000 символів.')
    if reason not in (None, '', 'release', 'transfer', 'version_closed', 'other'):
        raise ValueError('Невідома причина завершення.')
    return {**order_values(number, issued, 'release'), 'completion_reason': reason or None,
            'completion_note': (note or '').strip() or None}


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
        else:
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(current_schema()),hashtext('project2_organization'))"))
        db.info['project2_write']=True
        yield
        db.commit()
    except (IntegrityError, OperationalError, StaleDataError) as error:
        db.rollback()
        message = str(getattr(error, "orig", error))
        if "overlap" in message or getattr(getattr(error, "orig", None), "sqlstate", None) == "23P01":
            raise ValueError("Періоди перетинаються: перевірте історію та зайнятість.") from error
        if "outside version" in message:
            raise ValueError("Призначення виходить за період версії штату.") from error
        raise ValueError("Конфлікт або блокування БД. Оновіть дані й повторіть операцію.") from error
    except Exception:
        db.rollback()
        raise

    finally:
        db.info['project2_write']=False


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
    def create_assignment(db, person_id, position_id, start, end=None, *, order_number=None, order_date=None, release_number=None, release_date=None, completion_reason=None, completion_note=None, actor_id=None):
        period(start, end); official_start(start)
        with write_unit(db):
            checked(db, Person, person_id); target_position=checked(db, Position, position_id)
            from app.services.organization_staff import assert_position_period
            assert_position_period(db,target_position,start,end)
            record = PersonAssignment(person_id=person_id, staff_position_id=position_id, assigned_from=start, assigned_to=end, **order_values(order_number,order_date))
            StaffRepository.add(db, record); db.flush()
            for field, value in completion_values(release_number, release_date, completion_reason, completion_note).items(): setattr(record, field, value)
            record_change(db, record, 'create', actor_id=actor_id)
            key = record.id
        return key

    @staticmethod
    def correct_assignment(db, key, revision, person_id, position_id, start, end, *, details=None, actor_id=None):
        period(start, end)
        with write_unit(db):
            record = checked(db, PersonAssignment, key, revision)
            editable(record); official_start(start, record.assigned_from)
            before = audit_snapshot(record)
            checked(db, Person, person_id); target_position=checked(db, Position, position_id)
            from app.services.organization_staff import assert_position_period
            assert_position_period(db,target_position,start,end)
            record.person_id=person_id; record.staff_position_id=position_id
            record.assigned_from=start; record.assigned_to=end
            if details is not None:
                values = {**order_values(details.get('assignment_order_number'), details.get('assignment_order_date')),
                          **completion_values(details.get('release_order_number'), details.get('release_order_date'), details.get('completion_reason'), details.get('completion_note'))}
                for field, value in values.items(): setattr(record, field, value)
            record_change(db, record, 'edit', before, actor_id)
        return key

    @staticmethod
    def correct_position(db, key, revision, values):
        with write_unit(db):
            record=checked(db, Position, key, revision)
            if record.annulled_at:raise ValueError('Анульовані реквізити посади зберігаються незмінними.')
            current={name: getattr(record,name) for name in POSITION_ATTRIBUTES}
            if set(values) - set(current):
                raise ValueError("Можна виправити лише реквізити конкретної посади, без зміни версії.")
            current.update(values)
            for name,value in validate_position(current).items():
                setattr(record,name,value)
            db.flush()
        return key

    @staticmethod
    def close_version(db, key, revision, end, *, actor_id=None):
        exact_date(end)
        with write_unit(db):
            version=checked(db, StaffVersion, key, revision)
            if version.annulled_at:raise ValueError('Анульовану версію не можна закривати.')
            period(version.valid_from,end)
            if version.valid_to is not None and end > version.valid_to:
                raise ValueError("Закриття не подовжує період; для виправлення використайте редагування версії.")
            records=StaffRepository.assignments_for_version(db, key)
            if any(record.assigned_from>end for record in records):
                raise ValueError("Є призначення після обраного завершення. Спочатку виправте їхні періоди.")
            for record in records:
                if record.assigned_to is None or record.assigned_to>end:
                    before = audit_snapshot(record)
                    record.assigned_to=end
                    record.completion_reason="version_closed"
                    record_change(db, record, 'complete', before, actor_id, 'Закриття версії штату')
            db.flush()  # version guard must see already-closed assignment periods
            from app.repositories.organization_staff_repository import OrganizationStaffRepository as OrgRepo
            for coverage in OrgRepo.coverages(db):
                if coverage.staff_version_id==key and (coverage.valid_to is None or coverage.valid_to>end):
                    if coverage.valid_from>end:raise ValueError('Є пізніше покриття підрозділу; спочатку узгодьте його період.')
                    coverage.valid_to=end
            db.flush()
            version.valid_to=end
            db.flush()

    @staticmethod
    def correct_version(db, key, revision, name, start, end):
        period(start,end)
        with write_unit(db):
            record=checked(db,StaffVersion,key,revision)
            if record.annulled_at:raise ValueError('Анульовану версію не можна редагувати.')
            version_conflict(db,record.staff_structure_id,start,end,key)
            if not name.strip(): raise ValueError("Вкажіть назву версії.")
            record.name=name.strip();record.valid_from=start;record.valid_to=end
            db.flush()  # refuses periods invalidating any assignment

    @staticmethod
    def assignment_snapshot(db, position_id, person_id, on, orders=None):
        exact_date(on)
        target=checked(db,Position,position_id)
        from app.services.organization_staff import assert_position_period
        assert_position_period(db,target,on,on)
        version=checked(db,StaffVersion,target.staff_version_id)
        if on<version.valid_from or (version.valid_to and on>version.valid_to):
            raise ValueError("Обрана дата не належить періоду цієї версії.")
        source=StaffRepository.person_assignment_at(db, person_id, on) if person_id else None
        occupied=StaffRepository.position_assignment_at(db, position_id, on)
        if person_id is not None and (source is None or source.staff_position_id != position_id): official_start(on)
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
    def assign(db, position_id, person_id, on, expected, confirmed=False, *, actor_id=None):
        with write_unit(db):
            return StaffService._assign_locked(db,position_id,person_id,on,expected,confirmed,actor_id=actor_id)

    @staticmethod
    def _assign_locked(db, position_id, person_id, on, expected, confirmed=False, *, actor_id=None):
        snapshot=StaffService.assignment_snapshot(db,position_id,person_id,on,expected.get("orders"))
        for field in ('end', 'completion'):
            if field in expected: snapshot[field] = expected[field]
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
            before = audit_snapshot(old)
            old.assigned_to=on-timedelta(days=1)
            old.completion_reason="transfer" if person_id else "release"
            orders=expected.get('orders') or {}
            for key,value in order_values(orders.get('release_number'),date.fromisoformat(orders['release_date']) if orders.get('release_date') else None,'release').items():
                setattr(old,key,value)
            record_change(db, old, 'complete', before, actor_id, 'Переведення' if person_id else 'Звільнення з посади')
        if person_id is not None:
            position=checked(db,Position,position_id)
            version=checked(db,StaffVersion,position.staff_version_id)
            orders = expected.get('orders') or {}
            from app.services.organization_staff import effective_end,assert_position_period
            end = domain_date(expected['end'], False) if 'end' in expected else effective_end(db,position,version,on)
            assert_position_period(db,position,on,end)
            period(on, end)
            record = PersonAssignment(person_id=person_id, staff_position_id=position_id,
                assigned_from=on, assigned_to=end, **order_values(orders.get('number'), domain_date(orders.get('date'), False)))
            completion = dict(expected.get('completion') or {})
            if isinstance(completion.get('issued'), str): completion['issued'] = domain_date(completion['issued'], False)
            for field, value in completion_values(**completion).items(): setattr(record, field, value)
            StaffRepository.add(db, record)
            record_change(db, record, 'transfer' if old else 'create', actor_id=actor_id)
        return "Призначення збережено; історію попередньої посади збережено." if person_id else "Призначення завершено."

    @staticmethod
    def correct_orders(db, key, revision, assignment_number=_ORDER_UNSET, assignment_date=_ORDER_UNSET, release_number=_ORDER_UNSET, release_date=_ORDER_UNSET, *, actor_id=None):
        values={}
        for prefix,number,issued in [('assignment',assignment_number,assignment_date),('release',release_number,release_date)]:
            if number is not _ORDER_UNSET:values[prefix+'_order_number']=order_values(number,None,prefix)[prefix+'_order_number']
            if issued is not _ORDER_UNSET:
                exact_date(issued,False);values[prefix+'_order_date']=issued
        with write_unit(db):
            record=checked(db,PersonAssignment,key,revision)
            editable(record); before = audit_snapshot(record)
            for field,value in values.items():setattr(record,field,value)
            record_change(db, record, 'orders', before, actor_id)
        return key

    @staticmethod
    def release_assignment(db,key,revision,effective,number=None,issued=None,note=None,confirmed=False, *, actor_id=None):
        exact_date(effective)
        if not confirmed:raise ValueError('Підтвердьте звільнення саме з посади.')
        values=order_values(number,issued,'release')
        if len(note or '')>1000:raise ValueError('Примітка: максимум 1000 символів.')
        with write_unit(db):
            record=checked(db,PersonAssignment,key,revision)
            editable(record); before = audit_snapshot(record)
            if effective<=record.assigned_from:raise ValueError('Дата звільнення має бути пізніше першого дня призначення.')
            end=effective-timedelta(days=1)
            if (record.completion_reason and record.assigned_to!=end) or (record.assigned_to is not None and end>record.assigned_to):
                raise ValueError('Призначення вже завершене або дата виходить за його межі. Використайте виправлення історичних дат.')
            record.assigned_to=end;record.completion_reason='release';record.completion_note=(note or '').strip() or None
            for field,value in values.items():setattr(record,field,value)
            record_change(db, record, 'complete', before, actor_id, note)
        return key

    @staticmethod
    def annul_assignment(db, key, revision, reason, *, confirmed=False, actor_id=None):
        reason = (reason or '').strip()
        if not confirmed: raise ValueError('Підтвердьте анулювання призначення.')
        if not reason or len(reason) > 2000: raise ValueError('Причина анулювання обов’язкова: до 2000 символів.')
        with write_unit(db):
            StaffService.annul_assignment_locked(db,key,revision,reason,actor_id=actor_id)
        return key

    @staticmethod
    def annul_assignment_locked(db,key,revision,reason,*,actor_id=None):
        if not db.info.get('project2_write'):raise ValueError('Потрібна спільна кадрова транзакція.')
        reason=(reason or '').strip()
        if not reason or len(reason)>2000:raise ValueError('Причина анулювання обов’язкова: до 2000 символів.')
        record = checked(db, PersonAssignment, key, revision)
        editable(record); before = audit_snapshot(record)
        record.annulled_at = datetime.now(UTC)
        record.annulment_reason = reason; record.annulled_by = actor_id
        record_change(db, record, 'annul', before, actor_id, reason)
        return key

    @staticmethod
    def restore_assignment(db, key, revision, *, actor_id=None):
        with write_unit(db):
            record = checked(db, PersonAssignment, key, revision)
            if record.annulled_at is None: raise ValueError('Призначення вже не анульоване.')
            from app.services.organization_staff import assert_position_period
            assert_position_period(db,checked(db,Position,record.staff_position_id),record.assigned_from,record.assigned_to)
            # Restore the same existing period; no new or shifted future start.
            before = audit_snapshot(record)
            record.annulled_at = record.annulment_reason = record.annulled_by = None
            record_change(db, record, 'restore', before, actor_id)
        return key


def domain_date(raw, required=True):
    if not raw and not required:return None
    try:return date.fromisoformat(raw)
    except (ValueError,TypeError):raise ValueError('Потрібна точна дата у форматі РРРР-ММ-ДД.') from None

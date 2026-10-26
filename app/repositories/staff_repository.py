"""Staff persistence and queries. Period decisions stay in StaffService."""
from sqlalchemy import and_, or_
from app.models import StaffStructure, StaffVersion, Position, PersonAssignment


def active(model, start, end, on):
    return and_(getattr(model, start) <= on,
                or_(getattr(model, end).is_(None), getattr(model, end) >= on))


class StaffRepository:
    @staticmethod
    def get(db, model, key):
        return db.get(model, key)

    @staticmethod
    def add(db, record):
        db.add(record)
        return record

    @staticmethod
    def structures(db, *, ordered=False):
        query = db.query(StaffStructure)
        return (query.order_by(StaffStructure.code) if ordered else query).all()

    @staticmethod
    def versions(db, *, stable=False):
        query = db.query(StaffVersion).order_by(StaffVersion.valid_from.desc())
        return (query.order_by(StaffVersion.id) if stable else query).all()

    @staticmethod
    def structure_by_code(db, code):
        return db.query(StaffStructure).filter_by(code=code).one_or_none()

    @staticmethod
    def version_by_name(db, structure_id, name):
        return db.query(StaffVersion).filter_by(staff_structure_id=structure_id, name=name).first()

    @staticmethod
    def version_by_import_key(db, key):
        return db.query(StaffVersion).filter_by(import_key=key).first()

    @staticmethod
    def overlapping_version(db, structure_id, start, end, exclude=None):
        query = db.query(StaffVersion).filter(
            StaffVersion.staff_structure_id == structure_id,
            StaffVersion.valid_from <= end,
            or_(StaffVersion.valid_to.is_(None), StaffVersion.valid_to >= start))
        if exclude is not None:
            query = query.filter(StaffVersion.id != exclude)
        return query.first()

    @staticmethod
    def positions(db, version_id):
        return db.query(Position).filter_by(staff_version_id=version_id).order_by(Position.position_number).all()

    @staticmethod
    def all_positions(db):
        return (db.query(Position, StaffStructure, StaffVersion).select_from(Position)
                .join(StaffVersion, StaffVersion.id == Position.staff_version_id)
                .join(StaffStructure, StaffStructure.id == StaffVersion.staff_structure_id)
                .order_by(StaffVersion.valid_from.desc(), Position.position_number).all())

    @staticmethod
    def assignments_for_version(db, version_id):
        return (db.query(PersonAssignment).join(Position)
                .filter(Position.staff_version_id == version_id).all())

    @staticmethod
    def assignment_history(db, version_id):
        return (db.query(PersonAssignment, Position).join(Position)
                .filter(Position.staff_version_id == version_id)
                .order_by(PersonAssignment.assigned_from, PersonAssignment.id).all())

    @staticmethod
    def assignments_at(db, on):
        return (db.query(PersonAssignment).join(Position).join(StaffVersion)
                .filter(active(PersonAssignment, "assigned_from", "assigned_to", on),
                        active(StaffVersion, "valid_from", "valid_to", on)))

    @staticmethod
    def person_assignment_at(db, person_id, on):
        return StaffRepository.assignments_at(db, on).filter(PersonAssignment.person_id == person_id).one_or_none()

    @staticmethod
    def position_assignment_at(db, position_id, on):
        return StaffRepository.assignments_at(db, on).filter(PersonAssignment.staff_position_id == position_id).one_or_none()

    @staticmethod
    def person_ids_at_version(db, version_id, on):
        return [item.person_id for item in StaffRepository.assignments_at(db, on)
                .filter(StaffVersion.id == version_id)]

    @staticmethod
    def assignment_period_rows(db, person_id, start, end):
        query = (db.query(PersonAssignment, Position, StaffVersion).select_from(PersonAssignment)
                 .join(Position, Position.position_id == PersonAssignment.staff_position_id)
                 .join(StaffVersion, StaffVersion.id == Position.staff_version_id)
                 .filter(PersonAssignment.person_id == person_id,
                         or_(PersonAssignment.assigned_to.is_(None), PersonAssignment.assigned_to >= start)))
        if end:
            query = query.filter(PersonAssignment.assigned_from <= end)
        return query.order_by(PersonAssignment.assigned_from).all()

"""Read use cases for staff pages, independent of HTTP and Jinja."""
from datetime import date
from app.models import StaffVersion, Position, PersonAssignment
from app.repositories.staff_repository import StaffRepository
from app.services.staff_service import StaffService, today
from app.services.person_picker import person_options


def table_context(db, version_id=None, on=None):
    structures = StaffRepository.structures(db, ordered=True)
    versions = StaffRepository.versions(db, stable=True)
    chosen = next((item for item in versions if item.id == version_id), None)
    if version_id is not None and chosen is None:
        raise ValueError("Версія не існує.")
    if chosen is None and structures:
        current = today()
        preferred = sorted(structures, key=lambda item: (item.code != "main", item.code))
        chosen = next((version for structure in preferred for version in versions
                       if version.staff_structure_id == structure.id
                       and version.valid_from <= current <= (version.valid_to or date.max)), None)
    if on is None:
        on = today()
        if chosen:
            on = max(chosen.valid_from, min(on, chosen.valid_to or date.max))
    if chosen and not chosen.valid_from <= on <= (chosen.valid_to or date.max):
        raise ValueError("Дата перегляду не належить періоду версії.")
    return structures, versions, chosen, on


def history_context(db, version_id=None):
    versions = StaffRepository.versions(db)
    chosen = StaffRepository.get(db, StaffVersion, version_id) if version_id else (versions[0] if versions else None)
    structures = StaffRepository.structures(db)
    return {"versions": versions, "chosen": chosen,
            "positions": StaffRepository.positions(db, chosen.id) if chosen else [],
            "records": StaffRepository.assignment_history(db, chosen.id) if chosen else [],
            "all_positions": [(position, f"{structure.name} ({structure.code}) · {version.name}")
                              for position, structure, version in StaffRepository.all_positions(db)],
            "people": person_options(db, today()), "structures": structures,
            "structure_names": {item.id: f"{item.name} ({item.code})" for item in structures}}


def assignment_preview(db, position_id, person_id, on):
    snapshot = StaffService.assignment_snapshot(db, position_id, person_id, on)
    target = StaffRepository.get(db, Position, position_id)
    source = StaffRepository.get(db, PersonAssignment, snapshot['source'][0]) if snapshot['source'] else None
    previous = StaffRepository.get(db, Position, source.staff_position_id) if source else None
    return snapshot, person_options(db, on), target, source, previous


def position_version_id(db, key):
    return StaffRepository.get(db, Position, key).staff_version_id

from datetime import date
from sqlalchemy import event
from sqlalchemy.orm import Session
from app.models import StaffStructure, StaffVersion, Position, PersonAssignment


def install_legacy_staff_fixture():
    if event.contains(Session,"before_flush",supply_legacy_periods):return
    event.listen(Session,"before_flush",supply_legacy_periods)


def supply_legacy_periods(db,context,instances):
    if not db.info.get("legacy_staff_fixture"):return
    missing=[obj for obj in db.new if isinstance(obj,Position) and obj.staff_version_id is None and obj.staff_version is None]
    if missing:
        version=db.query(StaffVersion).filter_by(name="Synthetic regression staff").first()
        if version is None:
            version=next((obj for obj in db.new if isinstance(obj,StaffVersion) and obj.name=="Synthetic regression staff"),None)
        if version is None:
            version=StaffVersion(name="Synthetic regression staff",valid_from=date(2000,1,1),
                                 structure=StaffStructure(code="synthetic-regression",name="Synthetic regression staff"))
            db.add(version)
        for position in missing:position.staff_version=version
    for obj in db.new:
        if isinstance(obj,PersonAssignment) and obj.assigned_from is None:obj.assigned_from=date(2000,1,1)

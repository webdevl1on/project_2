from app.models.reference_data.ranks import ReferenceRanks
from app.models.reference_book import Rank, Position


def seed_ranks(db):
    for rank_data in ReferenceRanks.RANKS:
        existing_rank = (
            db.query(Rank)
            .filter(Rank.code == rank_data["code"])
            .first()
        )
        if existing_rank:
            print("ВЖЕ ІСНУЄ:", rank_data["code"])
            continue
        rank = Rank(**rank_data)
        db.add(rank)

    print("=== SEED RANKS END ===")


def seed_positions(db, excel_path, *, version_name, valid_from, valid_to=None, structure_code="main"):
    from app.models.staff import StaffStructure, StaffVersion
    from app.services.staff_import import preview_import, insert_prepared, read_positions
    from app.services.staff_service import POSITION_ATTRIBUTES
    structure = db.query(StaffStructure).filter_by(code=structure_code).one_or_none()
    if structure is None:
        structure=StaffStructure(code=structure_code,name=structure_code)
        db.add(structure); db.flush()
    existing=db.query(StaffVersion).filter_by(staff_structure_id=structure.id,name=version_name).one_or_none()
    if existing:
        data=read_positions(excel_path)
        if data["errors"]: raise ValueError("; ".join(data["errors"]))
        stored=[{key:getattr(position,key) for key in POSITION_ATTRIBUTES} for position in
                db.query(Position).filter_by(staff_version_id=existing.id).order_by(Position.position_number)]
        if existing.valid_from!=valid_from or existing.valid_to!=valid_to or stored!=sorted(data["positions"],key=lambda row:row["position_number"]):
            raise ValueError("Версія вже існує з іншими даними; автоматичне перезаписування заборонено.")
        return existing.id
    prepared=preview_import(db,excel_path,structure.id,version_name,valid_from,valid_to,valid_to is None)
    if prepared["errors"]: raise ValueError("; ".join(prepared["errors"]))
    import hashlib
    key=hashlib.sha256((structure_code+"|"+version_name+"|"+valid_from.isoformat()).encode()).hexdigest()
    return insert_prepared(db,prepared,key)

from csv import excel
from pathlib import Path
import re
import pandas as pd
from app.models.reference_data.ranks import ReferenceRanks
from app.models.reference_book import Rank, Position
from app.validators.position_validator import PositionValidator


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


def normalize_columns(columns) -> list[str]:
    normalized = []
    for col in columns:
        col = col.strip().lower()
        col = col.replace(" ", "_")
        col = col.replace("-", "_")
        normalized.append(col)
    return normalized

def load_positions(
        excel_path: Path,
        sheet_name: str = "positions"
    ) -> pd.DataFrame:

    df = pd.read_excel(
        excel_path,
        sheet_name=sheet_name,
        header=0,
        skiprows=[1],
        dtype=str,
        keep_default_na=False,
    )
    df.columns = normalize_columns(df.columns)
    return df

def seed_positions(db, excel_path: Path):
    df = load_positions(excel_path)

    for _, row in df.iterrows():
        position_number = PositionValidator.validate_position_number(
            row["position_number"]
        )

        position_data = {
            "position_number": position_number,
            "code": PositionValidator.validate_required_text(
                row["code"]
            ).upper(),
            "unit_short": PositionValidator.validate_required_text(
                row["unit_short"]
            ),
            "name_short": PositionValidator.validate_required_text(
                row["name_short"]
            ),
            "name_nominative": PositionValidator.validate_required_text(
                row["name_nominative"]
            ),
            "name_genitive": PositionValidator.validate_required_text(
                row["name_genitive"]
            ),
            "name_dative": PositionValidator.validate_required_text(
                row["name_dative"]
            ),
            "name_accusative": PositionValidator.validate_required_text(
                row["name_accusative"]
            ),
            "name_instrumental": PositionValidator.validate_required_text(
                row["name_instrumental"]
            ),
            "name_locative": PositionValidator.validate_required_text(
                row["name_locative"]
            ),
            "name_vocative": PositionValidator.validate_required_text(
                row["name_vocative"]
            ),
        }

        existing_position = (
            db.query(Position)
            .filter(
                Position.position_number == position_number
            )
            .first()
        )

        if existing_position:
            for field, value in position_data.items():
                setattr(existing_position, field, value)
        else:
            db.add(Position(**position_data))

    print("=== SEED POSITIONS END ===")


from app.models.reference_book import Rank
from app.models.reference_data.ranks import ReferenceRanks


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




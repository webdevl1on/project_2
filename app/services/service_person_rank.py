from app import models
from app.models.person_military_service import PersonRank
from app.models.reference_book import Rank
from app.services.service_person_checking import ServicePersonCheck
from app.validators.person_validator import PersonValidator

from app.services.service_person_group_data_validation import DataGroupValidate



#add and another RANK functions
class ServicePersonRankFunc:
    @staticmethod
    def add_rank(
        person_id,
        data,
        db,
    ):
        ServicePersonCheck.get_person_or_raise(person_id, db)

        rank_id = data.get("rank_id")

        if not rank_id:
            raise ValueError("Rank is required!")

        rank = (
            db.query(Rank)
            .filter(Rank.rank_id == rank_id)
            .first()
        )

        if not rank:
            raise ValueError("Selected rank was not found.")

        same_rank = (
            db.query(PersonRank)
            .filter(
                PersonRank.person_id == person_id,
                PersonRank.rank_id == rank_id,
            )
            .first()
        )

        if same_rank:
            raise ValueError("This rank is already exist")

        current_rank = (
            db.query(PersonRank)
            .filter(
                PersonRank.person_id == person_id,
                PersonRank.is_active.is_(True),
            )
            .first()
        )

        person_rank = PersonRank(
            person_id=person_id,
            rank_id=rank_id,
            rank_order_number=data.get("rank_order_number"),
            rank_order_date=data.get("rank_order_date"),
            is_active=False,
        )

        if not current_rank:
            person_rank.is_active = True

        db.add(person_rank)
        db.commit()
        db.refresh(person_rank)

        return person_rank



    @staticmethod
    def update_person_rank(person_rank_id, data, db):

        person_rank = (
            db.query(PersonRank)
            .filter(
                PersonRank.person_rank_id == person_rank_id,
            )
            .first()
        )

        if not person_rank:
            raise ValueError("Person rank record was not found.")

        rank_id = data.get("rank_id")

        if not rank_id:
            raise ValueError("Rank is required!")

        rank = (
            db.query(Rank)
            .filter(Rank.rank_id == rank_id)
            .first()
        )

        if not rank:
            raise ValueError("Selected rank was not found.")

        person_rank.rank_id = rank_id
        person_rank.rank_order_number = data.get("rank_order_number")
        person_rank.rank_order_date = data.get("rank_order_date")

        db.commit()
        db.refresh(person_rank)

        return person_rank



    @staticmethod
    def delete_person_rank(person_rank_id, confirmation, db):
        if confirmation != "DELETE":
            raise ValueError("Для видалення введіть DELETE")

        person_rank = (db.query(PersonRank)
                       .filter(PersonRank.person_rank_id == person_rank_id)
                       .first()
        )
        if not person_rank:
            raise ValueError("Person name not found")  
        person_id = person_rank.person_id
        db.delete(person_rank)
        db.commit()
        return person_id

    @staticmethod
    def change_person_rank(person_id, data, db):
        ServicePersonCheck.get_person_or_raise(person_id, db)
        current_rank = (
            db.query(PersonRank)
            .filter(PersonRank.person_id == person_id,
                    PersonRank.date_to.is_(None))
            .first()
        )
        if not current_rank:
            raise ValueError("Current person rank was not found")
        validated_data = {}
        if data.get("rank"):
            validated_data['rank'] = PersonValidator.validate_person_rank(data.get("rank"))
        if data.get("rank_order_number"):
            validated_data['rank'] = PersonValidator.validate_person_rank(data.get("rank_order_number"))
        if data.get("rank_order_date"):
            validated_data['rank_order_date'] = PersonValidator.validate_date(data.get("rank_order_date"))
        
        new_person_rank = PersonRank(
            person_id = person_id,
            rank = validated_data.get('rank'),
            rank_order_number = validated_data.get('rank_order_number'),
            rank_order_date = validated_data.get('rank_order_date'),
            
        )
        db.add(new_person_rank)
        db.commit()
        db.refresh(new_person_rank)
        return new_person_rank


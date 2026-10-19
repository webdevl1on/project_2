from app import models
from app.models.person_military_service import PersonRank
from app.models.reference_book import Rank
from app.services.service_person_checking import ServicePersonCheck
from app.validators.person_validator import PersonValidator

from app.services.service_person_group_data_validation import DataGroupValidate
from app.date_fields import DATE_FIELDS
from app.utils.date_utils import date_values_from_input



#add and another RANK functions
class ServicePersonRankFunc:
    @staticmethod
    def _get_rank_or_raise(rank_id, db):
        if not rank_id:
            raise ValueError("Оберіть звання.")

        rank = db.get(Rank, rank_id)
        if not rank:
            raise ValueError("Обране звання не знайдено.")
        return rank

    @staticmethod
    def _get_rank_data(data, current=None):
        return {
            "rank_order_number": PersonValidator.validate_person_rank(
                data.get("rank_order_number")
            ),
            **date_values_from_input(DATE_FIELDS["rank.rank_order_date"], "rank_order", data, current=current),
        }

    @staticmethod
    def add_rank(
        person_id,
        data,
        db,
    ):
        ServicePersonCheck.get_person_or_raise(person_id, db)

        rank_id = data.get("rank_id")
        ServicePersonRankFunc._get_rank_or_raise(rank_id, db)
        rank_data = ServicePersonRankFunc._get_rank_data(data)

        same_rank = (
            db.query(PersonRank)
            .filter(
                PersonRank.person_id == person_id,
                PersonRank.rank_id == rank_id,
            )
            .first()
        )

        if same_rank:
            raise ValueError("Таке звання вже є в історії людини.")

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
            **rank_data,
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
        ServicePersonRankFunc._get_rank_or_raise(rank_id, db)
        rank_data = ServicePersonRankFunc._get_rank_data(data, current=person_rank)

        person_rank.rank_id = rank_id
        for key, value in rank_data.items():
            setattr(person_rank, key, value)

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
        if person_rank.is_active:
            raise ValueError("Не можна видалити активне звання.")
        person_id = person_rank.person_id
        db.delete(person_rank)
        db.commit()
        return person_id

    @staticmethod
    def change_person_rank_to_active(person_rank_id, db):
        new_active_rank = db.get(PersonRank, person_rank_id)
        if not new_active_rank:
            raise ValueError("Запис про звання не знайдено.")

        current_rank = (
            db.query(PersonRank)
            .filter(
                PersonRank.person_id == new_active_rank.person_id,
                PersonRank.is_active.is_(True),
                PersonRank.person_rank_id != person_rank_id,
            )
            .first()
        )
        if current_rank:
            current_rank.is_active = False

        new_active_rank.is_active = True
        db.commit()
        return new_active_rank.person_id


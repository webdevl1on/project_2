from app.repositories.person_repository import PersonRepository
from app.database.transactions import service_transaction
from app.services.service_person_checking import ServicePersonCheck
from app.validators.person_validator import PersonValidator

from app.date_fields import DATE_FIELDS
from app.utils.date_utils import date_values_from_input



#add and another RANK functions
class ServicePersonRankFunc:
    @staticmethod
    def get_record(key, db):
        return PersonRepository.get_person_rank(db, key)

    @staticmethod
    def _get_rank_or_raise(rank_id, db):
        if not rank_id:
            raise ValueError("Оберіть звання.")

        rank = PersonRepository.get_rank(db, rank_id)
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
        *, commit=True
    ):
        with service_transaction(db, commit=commit):
            ServicePersonCheck.get_person_or_raise(person_id, db)

            rank_id = data.get("rank_id")
            ServicePersonRankFunc._get_rank_or_raise(rank_id, db)
            rank_data = ServicePersonRankFunc._get_rank_data(data)

            same_rank = PersonRepository.person_rank_by_rank(db, person_id, rank_id)

            if same_rank:
                raise ValueError("Таке звання вже є в історії людини.")

            current_rank = PersonRepository.current_rank(db, person_id)

            person_rank = PersonRepository.add_rank(db, person_id, dict(
                rank_id=rank_id,
                **rank_data,
                is_active=False,
            ))

            if not current_rank:
                person_rank.is_active = True

        db.refresh(person_rank)

        return person_rank



    @staticmethod
    def update_person_rank(person_rank_id, data, db, *, commit=True):

        with service_transaction(db, commit=commit):
            person_rank = PersonRepository.get_person_rank(db, person_rank_id)

            if not person_rank:
                raise ValueError("Person rank record was not found.")

            rank_id = data.get("rank_id")
            ServicePersonRankFunc._get_rank_or_raise(rank_id, db)
            rank_data = ServicePersonRankFunc._get_rank_data(data, current=person_rank)

            person_rank.rank_id = rank_id
            for key, value in rank_data.items():
                setattr(person_rank, key, value)

        db.refresh(person_rank)

        return person_rank



    @staticmethod
    def delete_person_rank(person_rank_id, confirmation, db, *, commit=True):
        with service_transaction(db, commit=commit):
            if confirmation != "DELETE":
                raise ValueError("Для видалення введіть DELETE")

            person_rank = PersonRepository.get_person_rank(db, person_rank_id)
            if not person_rank:
                raise ValueError("Person name not found")
            if person_rank.is_active:
                raise ValueError("Не можна видалити активне звання.")
            person_id = person_rank.person_id
            PersonRepository.delete(db, person_rank)
        return person_id

    @staticmethod
    def change_person_rank_to_active(person_rank_id, db, *, commit=True):
        with service_transaction(db, commit=commit):
            new_active_rank = PersonRepository.get_person_rank(db, person_rank_id)
            if not new_active_rank:
                raise ValueError("Запис про звання не знайдено.")

            current_rank = PersonRepository.current_rank(db, new_active_rank.person_id, exclude=person_rank_id)
            if current_rank:
                current_rank.is_active = False

            new_active_rank.is_active = True
        return new_active_rank.person_id

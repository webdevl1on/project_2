from sqlalchemy import and_
from app import models
from app.models.person import Person
from app.models.person_identity import PersonName
from app.models.person_military_service import PersonRank
from app.models.reference_book import Rank
from app.models.reference_book import Position
from app.models.person_positions import PersonPosition


class ServicePersonPositionFunc:

    @staticmethod
    def get_positions(
        db,
        unit_short: str | None = None,
        occupancy: str = "all",
        sort_by: str = "position_number",
        direction: str = "asc",
    ):
        # Дозволені поля сортування
        sort_columns = {
            "position_number": Position.position_number,
            "unit_short": Position.unit_short,
            "name_short": Position.name_short,
            "name_nominative": Position.name_nominative,
        }

        # Не дозволяємо передавати довільні назви колонок
        sort_column = sort_columns.get(
            sort_by,
            Position.position_number,
        )

        order = (
            sort_column.desc()
            if direction == "desc"
            else sort_column.asc()
        )

        # Основний запит: усі посади, навіть вільні
        query = (
            db.query(
                Position,
                PersonPosition,
                Person,
                PersonName,
                PersonRank,
                Rank,
            )
            .outerjoin(
                PersonPosition,
                Position.position_id == PersonPosition.position_id,
            )
            .outerjoin(
                Person,
                PersonPosition.person_id == Person.person_id,
            )
            .outerjoin(
                PersonName,
                and_(
                    PersonName.person_id == Person.person_id,
                    PersonName.is_active.is_(True),
                ),
            )
            .outerjoin(
                PersonRank,
                and_(
                    PersonRank.person_id == Person.person_id,
                    PersonRank.is_active.is_(True),
                ),
            )
            .outerjoin(
                Rank,
                PersonRank.rank_id == Rank.rank_id,
            )
        )

        # Фільтр за підрозділом
        if unit_short:
            query = query.filter(Position.unit_short == unit_short)

        # Фільтр за зайнятістю
        if occupancy == "occupied":
            query = query.filter(
                PersonPosition.person_position_id.is_not(None)
            )
        elif occupancy == "vacant":
            query = query.filter(
                PersonPosition.person_position_id.is_(None)
            )

        # Сортування та отримання результатів
        records = (
            query
            .order_by(order, Position.position_number)
            .all()
        )

        rows = [
            {
                "position": position,
                "assignment": assignment,
                "person": person,
                "name": name,
                "person_rank": person_rank,
                "rank": rank,
            }
            for (
                position,
                assignment,
                person,
                name,
                person_rank,
                rank,
            ) in records
        ]

        total = len(rows)
        occupied = sum(
            1 for row in rows
            if row["assignment"] is not None
        )
        vacant = total - occupied

        # Варіанти для фільтра підрозділу
        units = [
            unit[0]
            for unit in (
                db.query(Position.unit_short)
                .distinct()
                .order_by(Position.unit_short)
                .all()
            )
        ]

        return {
            "rows": rows,
            "units": units,
            "total": total,
            "occupied": occupied,
            "vacant": vacant,
        }


    @staticmethod
    def assign_person_to_position(
        position_id: int,
        person_id: int | None,
        db,
    ):
        position = db.get(Position, position_id)
        if not position:
            raise ValueError("Штатну позицію не знайдено")

        if person_id is not None:
            person = db.get(Person, person_id)
            if not person:
                raise ValueError("Військовослужбовця не знайдено")

        try:
            # Знаходимо поточне призначення цієї позиції
            target_assignment = (
                db.query(PersonPosition)
                .filter(
                    PersonPosition.position_id == position_id
                )
                .first()
            )

            # Якщо вибрали порожнє значення — звільняємо позицію
            if person_id is None:
                if target_assignment:
                    db.delete(target_assignment)

                db.commit()
                return None

            # Якщо людина вже займає іншу позицію — відв'язуємо її
            previous_assignment = (
                db.query(PersonPosition)
                .filter(
                    PersonPosition.person_id == person_id,
                    PersonPosition.position_id != position_id,
                )
                .first()
            )

            if previous_assignment:
                db.delete(previous_assignment)
                db.flush()

            # Призначаємо людину на вибрану позицію
            if target_assignment:
                target_assignment.person_id = person_id
            else:
                target_assignment = PersonPosition(
                    person_id=person_id,
                    position_id=position_id,
                )
                db.add(target_assignment)

            db.commit()
            db.refresh(target_assignment)

            return target_assignment

        except Exception:
            db.rollback()
            raise
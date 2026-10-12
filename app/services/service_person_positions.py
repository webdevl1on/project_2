from app import models
from app.models.person import Person
from app.models.reference_book import Position
from app.models.person_positions import PersonPosition

class ServicePersonPositionFunc:
     
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
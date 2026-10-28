"""Person-owned contacts; uniqueness applies only to active records."""
from sqlalchemy import String, ForeignKey, Index, CheckConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.base import Base
from app.models.staff import SystemTimestamps

class PersonContact(SystemTimestamps, Base):
    __tablename__ = 'person_contacts'
    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey('persons.person_id'), index=True)
    contact_type: Mapped[str] = mapped_column(String(10))
    value: Mapped[str] = mapped_column(String(320))
    normalized_value: Mapped[str] = mapped_column(String(320))
    label: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(String(1000))
    is_primary: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    __table_args__ = (
        CheckConstraint("contact_type IN ('phone','email')"),
        CheckConstraint("length(trim(value)) > 0 AND length(normalized_value) > 0"),
        CheckConstraint('NOT is_primary OR is_active'),
        CheckConstraint('is_primary IN (0,1) AND is_active IN (0,1)'),
        Index('one_primary_contact','person_id','contact_type',unique=True,sqlite_where=text('is_active = 1 AND is_primary = 1')),
        Index('unique_active_contact','person_id','contact_type','normalized_value',unique=True,sqlite_where=text('is_active = 1')),
    )

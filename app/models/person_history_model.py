from app.database.base import Base
from datetime import date, datetime, UTC
from typing import Optional
from sqlalchemy import (
    Boolean,
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    Text
)
from sqlalchemy.orm import Mapped, mapped_column

class HistoryModel(Base):
    __abstract__ = True
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC)
    )
    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )
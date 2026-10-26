from typing import Optional
from sqlalchemy import Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), index=True)
    clocked_in_at: Mapped[DateTime] = mapped_column(DateTime)
    clocked_out_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)
    token_hash: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)
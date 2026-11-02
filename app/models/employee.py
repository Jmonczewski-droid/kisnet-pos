from datetime import date, datetime
from typing import Optional
from sqlalchemy import Integer, String, Boolean, Date, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    location_id: Mapped[int] = mapped_column(Integer, default=1)
    number: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    code: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String)
    pin_hash: Mapped[str] = mapped_column(String)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    address: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    dob: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    hire_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    positions: Mapped[str] = mapped_column(String, default="")  # comma-separated list of roles this person can work
    ssn_last: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # the digit shown in the masked SSN
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # set when the employee is archived (terminated); never cleared
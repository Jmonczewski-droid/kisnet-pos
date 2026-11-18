from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LookinSession(Base):
    """A read-only sign-in to the look-in portal. Separate from station sessions: it needs no clock-in and it expires."""
    __tablename__ = "lookin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    employee_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

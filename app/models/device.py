from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Device(Base):
    """A printer or a monitor (kitchen/bar display) connected to this POS."""
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    location_id: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)  # "printer" | "monitor"
    jobs: Mapped[str] = mapped_column(String, default="")  # comma-separated: ticket tracks, plus "receipt" for printers
    host: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # printer: IP address or hostname
    port: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # printer: raw printing port (usually 9100)
    platform: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # monitor: PC, Android, Apple (seen at pairing)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    pairing_code: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)  # monitor: one-time code
    pairing_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    token_hash: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True)  # monitor: set once paired
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # last check-in or successful print
    last_error: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # printer: why the last print failed
    created_at: Mapped[datetime] = mapped_column(DateTime)

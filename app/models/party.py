from typing import Optional, List
from sqlalchemy import Integer, String, DateTime, ForeignKey, Index, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Party(Base):
    __tablename__ = "parties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    location_id: Mapped[int] = mapped_column(Integer, default=1)
    seat: Mapped[str] = mapped_column(String)  # e.g. "B2" or "Z3"
    party_name: Mapped[str] = mapped_column(String)
    party_size: Mapped[int] = mapped_column(Integer)
    server_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("employees.id"), nullable=True)
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"))
    opened_at: Mapped[DateTime] = mapped_column(DateTime)
    closed_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    # Relationships
    server: Mapped["Employee"] = relationship("Employee", foreign_keys=[server_id])
    orders: Mapped[List["Order"]] = relationship("Order", order_by="Order.id", back_populates="party")

    __table_args__ = (
        Index('ix_parties_seat', 'seat'),
        Index('ix_parties_closed_at', 'closed_at'),
    )
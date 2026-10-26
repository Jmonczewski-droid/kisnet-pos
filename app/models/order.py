from typing import Optional, List
from sqlalchemy import Integer, String, DateTime, ForeignKey, Enum, Boolean, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    location_id: Mapped[int] = mapped_column(Integer, default=1)
    party_id: Mapped[int] = mapped_column(Integer, ForeignKey("parties.id"), index=True)
    status: Mapped[str] = mapped_column(String)  # "open" | "completed"
    opened_at: Mapped[DateTime] = mapped_column(DateTime)
    completed_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    # Relationship
    items: Mapped[List["OrderItem"]] = relationship("OrderItem", order_by="OrderItem.id", cascade="all", back_populates="order")
    party: Mapped["Party"] = relationship("Party", back_populates="orders")


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("orders.id", ondelete="CASCADE"))
    menu_item_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("menu_items.id"), nullable=True)
    name: Mapped[str] = mapped_column(String)  # snapshot
    category: Mapped[str] = mapped_column(String)  # snapshot
    unit_price_cents: Mapped[int] = mapped_column(Integer)  # snapshot
    qty: Mapped[int] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    changed: Mapped[bool] = mapped_column(Boolean, default=False)  # True when edited after it was sent
    voided: Mapped[bool] = mapped_column(Boolean, default=False)  # removed from the order but kept so kitchen can see VOID until bumped
    created_by_id: Mapped[int] = mapped_column(Integer, ForeignKey("employees.id"))
    sent_at: Mapped[DateTime] = mapped_column(DateTime)
    bumped_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)

    # Relationship
    order: Mapped["Order"] = relationship("Order", back_populates="items")
    ingredients: Mapped[List["OrderItemIngredient"]] = relationship("OrderItemIngredient", cascade="all")


class OrderItemIngredient(Base):
    __tablename__ = "order_item_ingredients"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    order_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("order_items.id", ondelete="CASCADE"))
    ingredient: Mapped[str] = mapped_column(String)
    qty: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String)  # a SNAPSHOT of the recipe at sale time
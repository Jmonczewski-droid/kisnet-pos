from typing import List, Optional
from datetime import datetime
from sqlalchemy import Integer, String, Boolean, Float, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True)
    category: Mapped[str] = mapped_column(String)
    price_cents: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # set when the recipe is retired; never cleared
    
    recipe_lines: Mapped[List["RecipeLine"]] = relationship(
        "RecipeLine", 
        order_by="RecipeLine.id",
        cascade="all, delete-orphan"
    )


class RecipeLine(Base):
    __tablename__ = "recipe_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    menu_item_id: Mapped[int] = mapped_column(Integer, ForeignKey("menu_items.id", ondelete="CASCADE"))
    ingredient: Mapped[str] = mapped_column(String)
    qty: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String)
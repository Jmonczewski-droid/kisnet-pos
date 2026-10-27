from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, validator

from app.core.constants import CATEGORIES, ROLES


class EmployeeIn(BaseModel):
    name: str = Field(..., min_length=1)
    address: Optional[str] = None
    dob: Optional[date] = None
    hire_date: Optional[date] = None
    positions: List[str] = Field(..., min_length=1)
    pin: str = Field("1234", min_length=4)

    @validator("positions")
    def known_positions(cls, value):
        unknown = [position for position in value if position not in ROLES]
        if unknown:
            raise ValueError(f"unknown position(s): {', '.join(unknown)}")
        return value


class IngredientIn(BaseModel):
    ingredient: str = Field(..., min_length=1)
    qty: float = Field(..., gt=0)
    unit: str = Field(..., min_length=1)


class RecipeIn(BaseModel):
    name: str = Field(..., min_length=1)
    category: str
    price_cents: int = Field(..., ge=0)
    ingredients: List[IngredientIn] = Field(..., min_length=1)

    @validator("category")
    def known_category(cls, value):
        if value not in CATEGORIES:
            raise ValueError(f"category must be one of {', '.join(CATEGORIES)}")
        return value

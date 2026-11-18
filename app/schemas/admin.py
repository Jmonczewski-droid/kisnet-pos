from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field, validator

from app.core.constants import ACCESS_LEVELS, CATEGORIES, ROLES


def known_positions_validator(value):
    """Validate that all positions are in ROLES."""
    unknown = [position for position in value if position not in ROLES]
    if unknown:
        raise ValueError(f"unknown position(s): {', '.join(unknown)}")
    return value


def known_access_validator(value):
    if value is not None and value not in ACCESS_LEVELS:
        raise ValueError(f"access must be one of {', '.join(ACCESS_LEVELS)}")
    return value


class EmployeeIn(BaseModel):
    name: str = Field(..., min_length=1)
    address: Optional[str] = None
    dob: Optional[date] = None
    hire_date: Optional[date] = None
    positions: List[str] = Field(default_factory=list)  # stations; a manager or owner may have none
    access: Optional[str] = None  # owner | manager | team; when left out, "admin" in positions means manager
    pin: str = Field("1234", min_length=4)  # a starter PIN: the employee replaces it at first sign-in

    @validator("positions")
    def known_positions(cls, value):
        return known_positions_validator(value)

    @validator("access")
    def known_access(cls, value):
        return known_access_validator(value)


class EmployeeEdit(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    address: Optional[str] = None
    dob: Optional[date] = None
    hire_date: Optional[date] = None
    positions: Optional[List[str]] = None
    access: Optional[str] = None
    pin: Optional[str] = Field(None, min_length=4)

    @validator("access")
    def known_access(cls, value):
        return known_access_validator(value)

    @validator("positions")
    def known_positions(cls, value):
        if value is not None:
            return known_positions_validator(value)
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

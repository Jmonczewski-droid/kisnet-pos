from typing import Optional
from pydantic import BaseModel, Field, validator
from app.schemas.order import OrderOut
from app.core.constants import ALL_SEATS


class PartyIn(BaseModel):
    seat: str = Field(..., min_length=1)
    party_name: str = Field(..., min_length=1)
    party_size: Optional[int] = Field(None, ge=1)  # required at tables; bar seats do not record a size
    server_id: Optional[int] = None

    @validator('seat')
    def validate_seat(cls, v):
        if v not in ALL_SEATS:
            raise ValueError('Seat must be a valid seat code')
        return v


class PartySummary(BaseModel):
    id: int
    seat: str
    party_name: str
    party_size: int
    server_id: Optional[int]
    server_name: Optional[str]
    opened_at: str
    drinks_ready_at: Optional[str] = None  # when the bar last bumped this party's drinks

    class Config:
        from_attributes = True


class PartyDetail(PartySummary):
    closed_at: Optional[str]
    open_order: Optional[OrderOut]
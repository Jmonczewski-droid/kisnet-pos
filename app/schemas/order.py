from datetime import datetime
from typing import List, Optional, Union
from pydantic import BaseModel, Field
from app.core.constants import CATEGORIES


class OrderItemIn(BaseModel):
    menu_item_id: int
    qty: int = Field(ge=1)
    notes: Optional[str] = None


class OrderItemsIn(BaseModel):
    items: List[OrderItemIn]
    
    class Config:
        from_attributes = True
    
    @classmethod
    def model_validate(cls, data):
        if not data.get("items") or len(data["items"]) < 1:
            raise ValueError("At least one item must be provided")
        return super().model_validate(data)


class OrderItemPatch(BaseModel):
    qty: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = None


class OrderItemOut(BaseModel):
    id: int
    menu_item_id: int
    name: str
    category: str
    unit_price_cents: int
    qty: int
    notes: Optional[str] = None
    changed: bool
    voided: bool
    bumped: bool
    sent_at: datetime
    line_total_cents: int
    
    class Config:
        from_attributes = True


class TicketUpdateIn(BaseModel):
    item_id: int
    qty: Optional[int] = Field(None, ge=1)
    notes: Optional[str] = None


class TicketSendIn(BaseModel):
    items: List[OrderItemIn] = []
    updates: List[TicketUpdateIn] = []
    voids: List[int] = []


class OrderOut(BaseModel):
    id: int
    party_id: int
    status: str
    opened_at: datetime
    completed_at: Optional[datetime] = None
    total_cents: int
    items: List[OrderItemOut]
    
    class Config:
        from_attributes = True
from pydantic import BaseModel
from typing import List
from datetime import date


class DailySalesRow(BaseModel):
    name: str
    category: str
    qty: int
    sales_cents: int


class DailySalesOut(BaseModel):
    start: date
    end: date
    order_count: int
    total_qty: int
    total_sales_cents: int
    rows: List[DailySalesRow]


class FoodUsageRow(BaseModel):
    ingredient: str
    unit: str
    qty: float


class FoodUsageOut(BaseModel):
    start: date
    end: date
    rows: List[FoodUsageRow]
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ClockInIn(BaseModel):
    code: str
    pin: str
    position: Optional[str] = None  # the role this shift is worked in, when the employee has several


class EmployeeOut(BaseModel):
    id: int
    location_id: int
    number: int
    code: str
    name: str
    role: str
    active: bool

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    token: str
    employee: EmployeeOut


class ClockedOutOut(BaseModel):
    clocked_out: bool
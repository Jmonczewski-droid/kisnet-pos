from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ClockInIn(BaseModel):
    code: str
    pin: str


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
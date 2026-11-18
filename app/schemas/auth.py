from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ClockInIn(BaseModel):
    code: str
    pin: str
    position: Optional[str] = None  # the role this shift is worked in, when the employee has several
    otp: Optional[str] = None  # authenticator-app code, for an owner with two-step sign-in


class PinChangeIn(BaseModel):
    code: str
    pin: str
    new_pin: str = Field(..., min_length=4, max_length=64)


class OtpIn(BaseModel):
    otp: str = Field(..., min_length=6, max_length=12)


class EmployeeOut(BaseModel):
    id: int
    location_id: int
    number: int
    code: str
    name: str
    role: str
    active: bool
    access: str = "team"  # owner | manager | team

    class Config:
        from_attributes = True


class TokenOut(BaseModel):
    token: str
    employee: EmployeeOut


class ClockedOutOut(BaseModel):
    clocked_out: bool
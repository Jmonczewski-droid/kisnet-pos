from app.core.time import utcnow
from typing import Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from app.models.employee import Employee
from app.models.time_entry import TimeEntry
from app.core.security import verify_pin, new_token, hash_token
from fastapi import HTTPException, status


class SessionUser:
    """The signed-in person, acting in the role (position) of their current shift."""

    def __init__(self, employee: Employee, role: str):
        self._employee = employee
        self.role = role

    def __getattr__(self, name):
        return getattr(self._employee, name)


def employee_positions(employee: Employee) -> list:
    """The positions an employee can work; their role if none are listed."""
    return [p for p in (employee.positions or "").split(",") if p] or [employee.role]


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def check_pin(session: Session, code: str, pin: str) -> Employee:
    """Return the active employee for code+PIN, or raise AuthError. Has no side effects."""
    employee = session.query(Employee).filter_by(code=code).first()

    if not employee:
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Invalid code or PIN")

    if not employee.active:
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Employee is inactive")

    if not verify_pin(pin, employee.pin_hash):
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Invalid code or PIN")

    return employee


def preview_clock_in(session: Session, code: str, pin: str) -> dict:
    """Who is signing in, their positions, and whether they are already on the clock (for the confirmation pop-up)."""
    employee = check_pin(session, code, pin)
    entry = open_entry_for(session, employee.id)
    return {"employee": employee, "positions": employee_positions(employee),
            "on_clock": entry is not None, "clocked_in_at": entry.clocked_in_at if entry else None}


def clock_in(session: Session, code: str, pin: str, position: Optional[str] = None) -> TimeEntry:
    """Start a shift in one of the employee's positions. Clocking in does not log anyone in."""
    employee = check_pin(session, code, pin)
    if open_entry_for(session, employee.id):
        raise AuthError(status.HTTP_409_CONFLICT, "Already clocked in")
    positions = employee_positions(employee)
    if position is None:
        if len(positions) > 1:
            raise AuthError(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose the position you are clocking in as")
        position = positions[0]
    if position not in positions:
        raise AuthError(status.HTTP_422_UNPROCESSABLE_ENTITY, "That position is not on this employee's list")
    entry = TimeEntry(employee_id=employee.id, clocked_in_at=utcnow(), token_hash=None, position=position)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def login(session: Session, code: str, pin: str) -> Tuple[SessionUser, str]:
    """Open a station session in the position of the current shift. Only possible while on the clock."""
    employee = check_pin(session, code, pin)
    entry = open_entry_for(session, employee.id)
    if not entry:
        raise AuthError(status.HTTP_409_CONFLICT, "Not clocked in. Clock in first.")
    token = new_token()
    entry.token_hash = hash_token(token)
    session.commit()
    return SessionUser(employee, entry.position or employee.role), token


def logout(session: Session, employee: Employee) -> None:
    """End this session but leave the employee on the clock."""
    entry = open_entry_for(session, employee.id)
    if entry:
        entry.token_hash = None
        session.commit()


def clock_out(session: Session, employee: Employee) -> None:
    # Find the open time entry for this employee
    time_entry = session.query(TimeEntry).filter_by(employee_id=employee.id, clocked_out_at=None).first()
    
    if not time_entry:
        raise AuthError(status.HTTP_409_CONFLICT, "Employee not clocked in")
        
    # Set clock out time
    time_entry.clocked_out_at = utcnow()
    
    session.commit()
    session.refresh(time_entry)


def get_employee_by_token(session: Session, token: str) -> Optional[SessionUser]:
    """The signed-in person for this token, in their shift's position, or None if the session is not active."""
    entry = session.query(TimeEntry).filter_by(token_hash=hash_token(token)).first()
    if not entry or entry.clocked_out_at:
        return None
    employee = session.get(Employee, entry.employee_id)
    return SessionUser(employee, entry.position or employee.role) if employee else None


def open_entry_for(session: Session, employee_id: int) -> Optional[TimeEntry]:
    """Get the currently open time entry for an employee"""
    return session.query(TimeEntry).filter_by(employee_id=employee_id, clocked_out_at=None).first()
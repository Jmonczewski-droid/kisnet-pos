from app.core.time import utcnow
from typing import Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from app.models.employee import Employee
from app.models.time_entry import TimeEntry
from app.core.security import verify_pin, new_token, hash_token
from fastapi import HTTPException, status


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def clock_in(session: Session, code: str, pin: str) -> Tuple[Employee, str]:
    # Find employee by code
    employee = session.query(Employee).filter_by(code=code).first()
    
    if not employee:
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Invalid code or PIN")
        
    if not employee.active:
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Employee is inactive")

    # Verify PIN
    if not verify_pin(pin, employee.pin_hash):
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Invalid code or PIN")

    # Check if employee is already clocked in
    existing_entry = session.query(TimeEntry).filter_by(employee_id=employee.id, clocked_out_at=None).first()
    
    if existing_entry:
        raise AuthError(status.HTTP_409_CONFLICT, "Employee already clocked in")

    # Create new token and time entry
    token = new_token()
    token_hash = hash_token(token)
    
    time_entry = TimeEntry(
        employee_id=employee.id,
        clocked_in_at=utcnow(),
        token_hash=token_hash
    )
    
    session.add(time_entry)
    session.commit()
    session.refresh(time_entry)
    
    return employee, token


def clock_out(session: Session, employee: Employee) -> None:
    # Find the open time entry for this employee
    time_entry = session.query(TimeEntry).filter_by(employee_id=employee.id, clocked_out_at=None).first()
    
    if not time_entry:
        raise AuthError(status.HTTP_409_CONFLICT, "Employee not clocked in")
        
    # Set clock out time
    time_entry.clocked_out_at = utcnow()
    
    session.commit()
    session.refresh(time_entry)


def get_employee_by_token(session: Session, token: str) -> Optional[Employee]:
    """Get employee by token or return None if not found"""
    token_hash = hash_token(token)
    
    time_entry = session.query(TimeEntry).filter_by(token_hash=token_hash).first()
    
    if not time_entry:
        return None
    
    # Check if time entry has been clocked out
    if time_entry.clocked_out_at:
        return None
        
    return session.query(Employee).filter_by(id=time_entry.employee_id).first()


def open_entry_for(session: Session, employee_id: int) -> Optional[TimeEntry]:
    """Get the currently open time entry for an employee"""
    return session.query(TimeEntry).filter_by(employee_id=employee_id, clocked_out_at=None).first()
from typing import Generator
from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.models.employee import Employee
from app.models.time_entry import TimeEntry
from app.services.auth import get_employee_by_token


def get_current_employee(db: Session = Depends(get_db), authorization: str = Header(None)) -> Employee:
    """Get current employee from Authorization header"""
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    
    # Extract token from "Bearer <token>" format
    try:
        token = authorization.split(" ")[1]
    except (IndexError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization format")
    
    employee = get_employee_by_token(db, token)
    if not employee:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
    return employee


def require_roles(*roles: str):
    def _require_roles(current_employee: Employee = Depends(get_current_employee)) -> Employee:
        # Check if the employee has any of the required roles
        if current_employee.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
            
        return current_employee
    
    return _require_roles
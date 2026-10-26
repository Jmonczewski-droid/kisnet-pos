from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_current_employee, get_db, require_roles
from app.services.admin import list_employees, on_clock, force_clock_out
from app.models.employee import Employee


router = APIRouter()


@router.get("/employees")
async def get_employees(
    role: str | None = None,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
) -> List[dict]:
    """
    Get list of active employees, optionally filtered by role.
    
    Args:
        role: Optional role filter
        db: Database session
        current_employee: Current authenticated employee
        
    Returns:
        List of EmployeeOut objects for active employees sorted by name
    """
    employees = list_employees(db, role)
    
    # Return as list of dictionaries (matching EmployeeOut schema)
    return [
        {
            "id": emp.id,
            "code": emp.code,
            "name": emp.name,
            "role": emp.role
        }
        for emp in employees
    ]


@router.get("/admin/on-clock")
async def get_on_clock(
    db: Session = Depends(get_db),
    current_employee = Depends(require_roles("admin"))
) -> List[dict]:
    """
    Get list of employees currently on clock.
    
    Args:
        db: Database session
        current_employee: Current authenticated employee (must be admin)
        
    Returns:
        List of dictionaries with employee info for open time entries
    """
    return on_clock(db)


@router.post("/admin/clock-out/{employee_id}")
async def clock_out(
    employee_id: int,
    db: Session = Depends(get_db),
    current_employee = Depends(require_roles("admin"))
) -> dict:
    """
    Force clock out an employee.
    
    Args:
        employee_id: ID of employee to clock out
        db: Database session
        current_employee: Current authenticated employee (must be admin)
        
    Returns:
        Dictionary confirming clock out
        
    Raises:
        HTTPException: If employee is not on clock
    """
    try:
        force_clock_out(db, employee_id)
        return {"clocked_out": True}
    except ValueError:
        raise HTTPException(status_code=404, detail="Employee is not on clock")
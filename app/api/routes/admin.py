from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_employee, get_db, require_roles
from app.services.admin import (AdminError, add_employee, add_recipe, force_clock_out, list_employees,
                                on_clock, list_recipes, roster)
from app.schemas.admin import EmployeeIn, RecipeIn
from app.services.stats import day_stats
from app.services.daily_reports import end_of_day
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

@router.get("/admin/stats")
def get_day_stats(
    day: Optional[date] = Query(None, alias="date", description="Business day (default today)"),
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """Sales, active tickets, and labor by hour for one business day."""
    return day_stats(db, day)


@router.post("/admin/end-of-day")
def run_end_of_day(
    day: Optional[date] = Query(None, alias="date", description="Business day (default today)"),
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    """Export the business day's summary, item sales and hourly figures to CSV files on the server."""
    return end_of_day(db, day)


@router.get("/admin/roster")
def get_roster(_: Employee = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Every employee with positions, on-clock status and hours this week."""
    return roster(db)


@router.post("/admin/employees", status_code=201)
def create_employee(data: EmployeeIn, _: Employee = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Add an employee. The code is assigned from the main position."""
    employee = add_employee(db, data)
    return {"id": employee.id, "code": employee.code, "name": employee.name, "positions": employee.positions}


@router.get("/admin/recipes")
def get_recipes(_: Employee = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return list_recipes(db)


@router.post("/admin/recipes", status_code=201)
def create_recipe(data: RecipeIn, _: Employee = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Add a recipe with its price. Drinks go to the bar; food to the kitchen track of its category."""
    try:
        item = add_recipe(db, data)
    except AdminError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"id": item.id, "name": item.name, "category": item.category, "price_cents": item.price_cents}

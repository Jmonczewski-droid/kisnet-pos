from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_employee, get_db, require_roles
from app.services.admin import (AdminError, add_employee, add_recipe, force_clock_out, list_employees,
                                on_clock, list_recipes, roster, update_employee, deactivate_employee, reactivate_employee, archive_employee,
                                update_recipe, deactivate_recipe, reactivate_recipe, archive_recipe)
from app.schemas.admin import EmployeeIn, RecipeIn, EmployeeEdit
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
def get_roster(
    include_archived: bool = False,
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Every employee with positions, on-clock status and hours this week."""
    return roster(db, include_archived=include_archived)


@router.post("/admin/employees", status_code=201)
def create_employee(data: EmployeeIn, _: Employee = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Add an employee. The code is assigned from the main position."""
    employee = add_employee(db, data)
    return {"id": employee.id, "code": employee.code, "name": employee.name, "positions": employee.positions}


@router.patch("/admin/employees/{employee_id}")
def update_employee_endpoint(
    employee_id: int,
    data: EmployeeEdit,
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Update an employee's information."""
    try:
        updated_employee = update_employee(db, employee_id, data)
        # Return the single roster row for that employee
        roster_row = next(row for row in roster(db, include_archived=True) if row["id"] == employee_id)
        return roster_row
    except AdminError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/admin/employees/{employee_id}/deactivate")
def deactivate_employee_endpoint(
    employee_id: int,
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Deactivate an employee."""
    try:
        deactivated_employee = deactivate_employee(db, employee_id)
        # Return the single roster row for that employee
        roster_row = next(row for row in roster(db, include_archived=True) if row["id"] == employee_id)
        return roster_row
    except AdminError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/admin/employees/{employee_id}/reactivate")
def reactivate_employee_endpoint(
    employee_id: int,
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Reactivate an employee."""
    try:
        reactivated_employee = reactivate_employee(db, employee_id)
        # Return the single roster row for that employee
        roster_row = next(row for row in roster(db, include_archived=True) if row["id"] == employee_id)
        return roster_row
    except AdminError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/admin/employees/{employee_id}/archive")
def archive_employee_endpoint(
    employee_id: int,
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Archive an employee (permanently delete)."""
    try:
        archived_employee = archive_employee(db, employee_id)
        # Return the single roster row for that employee
        roster_row = next(row for row in roster(db, include_archived=True) if row["id"] == employee_id)
        return roster_row
    except AdminError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/admin/recipes")
def get_recipes(include_archived: bool = False, _: Employee = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return list_recipes(db, include_archived=include_archived)


@router.put("/admin/recipes/{recipe_id}")
def update_recipe_endpoint(
    recipe_id: int,
    data: RecipeIn,
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Update a recipe."""
    try:
        update_recipe(db, recipe_id, data)
    except AdminError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    
    # Return the updated recipe dict
    recipe_dict = next(r for r in list_recipes(db, include_archived=True) if r["id"] == recipe_id)
    return recipe_dict


@router.post("/admin/recipes/{recipe_id}/deactivate")
def deactivate_recipe_endpoint(
    recipe_id: int,
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Deactivate a recipe."""
    try:
        deactivated_recipe = deactivate_recipe(db, recipe_id)
    except AdminError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    
    # Return the updated recipe dict
    recipe_dict = next(r for r in list_recipes(db, include_archived=True) if r["id"] == recipe_id)
    return recipe_dict


@router.post("/admin/recipes/{recipe_id}/reactivate")
def reactivate_recipe_endpoint(
    recipe_id: int,
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Reactivate a recipe."""
    try:
        reactivated_recipe = reactivate_recipe(db, recipe_id)
    except AdminError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    
    # Return the updated recipe dict
    recipe_dict = next(r for r in list_recipes(db, include_archived=True) if r["id"] == recipe_id)
    return recipe_dict


@router.post("/admin/recipes/{recipe_id}/archive")
def archive_recipe_endpoint(
    recipe_id: int,
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    """Archive a recipe (permanently remove from menu)."""
    try:
        archived_recipe = archive_recipe(db, recipe_id)
    except AdminError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    
    # Return the updated recipe dict
    recipe_dict = next(r for r in list_recipes(db, include_archived=True) if r["id"] == recipe_id)
    return recipe_dict


@router.post("/admin/recipes", status_code=201)
def create_recipe(data: RecipeIn, _: Employee = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    """Add a recipe with its price. Drinks go to the bar; food to the kitchen track of its category."""
    try:
        item = add_recipe(db, data)
    except AdminError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    return {"id": item.id, "name": item.name, "category": item.category, "price_cents": item.price_cents}
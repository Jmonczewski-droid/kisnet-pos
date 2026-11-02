from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.constants import ROLES
from app.core.security import hash_pin
from app.services.auth import open_entry_for
from app.models.employee import Employee
from app.models.menu import MenuItem, RecipeLine
from app.models.time_entry import TimeEntry
from app.core.time import utcnow


def recipe_status(item) -> str:
    """Determine recipe status: archived, active, or inactive."""
    if item.archived_at is not None:
        return "archived"
    elif item.active:
        return "active"
    else:
        return "inactive"


def update_recipe(session: Session, recipe_id: int, data) -> MenuItem:
    """Update a menu item with new data and ingredients."""
    item = session.get(MenuItem, recipe_id)
    if not item:
        raise AdminError(404, "Recipe not found")
    
    if item.archived_at is not None:
        raise AdminError(409, "Archived recipes cannot be changed")
        
    # Check for duplicate name (excluding this recipe itself)
    name = data.name.strip() if hasattr(data, 'name') else item.name
    existing = session.query(MenuItem).filter(
        MenuItem.name == name,
        MenuItem.id != recipe_id
    ).first()
    if existing:
        raise AdminError(409, "A recipe with this name already exists")
    
    # Update the recipe fields
    if hasattr(data, 'name'):
        item.name = data.name.strip()
    if hasattr(data, 'category'):
        item.category = data.category
    if hasattr(data, 'price_cents'):
        item.price_cents = data.price_cents
    
    # Replace ingredients: clear current lines and add new ones
    item.recipe_lines.clear()
    if hasattr(data, 'ingredients'):
        for line in data.ingredients:
            item.recipe_lines.append(
                RecipeLine(
                    ingredient=line.ingredient.strip(),
                    qty=line.qty,
                    unit=line.unit.strip()
                )
            )
    
    session.commit()
    session.refresh(item)
    return item


def deactivate_recipe(session: Session, recipe_id: int) -> MenuItem:
    """Deactivate a recipe (removes it from menu)."""
    item = session.get(MenuItem, recipe_id)
    if not item:
        raise AdminError(404, "Recipe not found")
    
    if item.archived_at is not None:
        raise AdminError(409, "Archived recipes cannot be changed")
        
    if not item.active:
        raise AdminError(409, "Already inactive")
        
    item.active = False
    session.commit()
    session.refresh(item)
    return item


def reactivate_recipe(session: Session, recipe_id: int) -> MenuItem:
    """Reactivate a recipe (puts it back on the menu)."""
    item = session.get(MenuItem, recipe_id)
    if not item:
        raise AdminError(404, "Recipe not found")
        
    if item.archived_at is not None:
        raise AdminError(409, "Archived recipes cannot be reactivated")
        
    if item.active:
        raise AdminError(409, "Already active")
        
    item.active = True
    session.commit()
    session.refresh(item)
    return item


def archive_recipe(session: Session, recipe_id: int) -> MenuItem:
    """Archive a recipe (removes it permanently from the menu and history)."""
    item = session.get(MenuItem, recipe_id)
    if not item:
        raise AdminError(404, "Recipe not found")
        
    if item.archived_at is not None:
        raise AdminError(409, "Already archived")
        
    item.active = False
    item.archived_at = utcnow()
    session.commit()
    session.refresh(item)
    return item


def list_recipes(session: Session, include_archived: bool = False) -> List[dict]:
    """List recipes, optionally including archived ones."""
    query = session.query(MenuItem).order_by(MenuItem.category, MenuItem.name)
    
    if not include_archived:
        query = query.filter(MenuItem.archived_at.is_(None))
    
    result = []
    for item in query.all():
        recipe_dict = {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "price_cents": item.price_cents,
            "ingredients": [{"ingredient": line.ingredient, "qty": line.qty, "unit": line.unit} for line in item.recipe_lines],
            "status": recipe_status(item)
        }
        result.append(recipe_dict)
    
    return result


def employee_status(employee) -> str:
    """Determine employee status: archived, active, or inactive."""
    if employee.archived_at is not None:
        return "archived"
    elif employee.active:
        return "active"
    else:
        return "inactive"


def update_employee(session: Session, employee_id: int, data) -> Employee:
    """Update an employee with the given data. Only fields sent are updated."""
    employee = session.get(Employee, employee_id)
    if not employee:
        raise AdminError(404, "Employee not found")
    
    if employee.archived_at is not None:
        raise AdminError(409, "Archived employees cannot be changed")
        
    # Apply only the fields sent
    update_data = data.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        if key == "name":
            setattr(employee, key, value.strip())
        elif key == "pin":
            setattr(employee, "pin_hash", hash_pin(value))
        elif key == "positions":
            # Order by ROLES as add_employee does
            ordered_positions = [role for role in ROLES if role in value]
            setattr(employee, "role", ordered_positions[0] if ordered_positions else employee.role)
            setattr(employee, "positions", ",".join(ordered_positions) if ordered_positions else employee.positions)
        else:
            setattr(employee, key, value)
    
    session.commit()
    session.refresh(employee)
    return employee


def _leave_job(session: Session, employee) -> None:
    """Helper to handle leaving a job (clock out and close open tables)."""
    # Clock out if there's an open time entry
    open_entry = (
        session.query(TimeEntry)
        .filter(
            TimeEntry.employee_id == employee.id,
            TimeEntry.clocked_out_at.is_(None)
        )
        .first()
    )
    
    if open_entry:
        open_entry.clocked_out_at = utcnow()
    
    # Check for open parties
    from app.models.party import Party
    open_party = (
        session.query(Party)
        .filter(
            Party.server_id == employee.id,
            Party.closed_at.is_(None)
        )
        .first()
    )
    
    if open_party:
        raise AdminError(409, "Close or move this employee's open tables first")


def deactivate_employee(session: Session, employee_id: int) -> Employee:
    """Deactivate an employee."""
    employee = session.get(Employee, employee_id)
    if not employee:
        raise AdminError(404, "Employee not found")
    
    if employee.archived_at is not None:
        raise AdminError(409, "Archived employees cannot be changed")
        
    if not employee.active:
        raise AdminError(409, "Already inactive")
        
    _leave_job(session, employee)
    employee.active = False
    session.commit()
    session.refresh(employee)
    return employee


def reactivate_employee(session: Session, employee_id: int) -> Employee:
    """Reactivate an employee."""
    employee = session.get(Employee, employee_id)
    if not employee:
        raise AdminError(404, "Employee not found")
        
    if employee.archived_at is not None:
        raise AdminError(409, "Archived employees cannot be reactivated")
        
    if employee.active:
        raise AdminError(409, "Already active")
        
    employee.active = True
    session.commit()
    session.refresh(employee)
    return employee


def archive_employee(session: Session, employee_id: int) -> Employee:
    """Archive an employee (permanent deletion)."""
    employee = session.get(Employee, employee_id)
    if not employee:
        raise AdminError(404, "Employee not found")
        
    if employee.archived_at is not None:
        raise AdminError(409, "Already archived")
        
    _leave_job(session, employee)
    employee.active = False
    employee.archived_at = utcnow()
    session.commit()
    session.refresh(employee)
    return employee


def roster(session: Session, include_archived: bool = False) -> List[dict]:
    """Get employee roster with status information."""
    from app.services.timecard import employee_week
    query = session.query(Employee).order_by(Employee.name)

    if not include_archived:
        query = query.filter(Employee.archived_at.is_(None))

    result = []
    for employee in query.all():
        entry = open_entry_for(session, employee.id)
        row = {
            "id": employee.id,
            "code": employee.code,
            "name": employee.name,
            "positions": [p for p in (employee.positions or "").split(",") if p] or [employee.role],
            "address": employee.address,
            "dob": employee.dob,
            "hire_date": employee.hire_date,
            "ssn": f"XXX-XX-XXX{employee.ssn_last or ''}",
            "active": employee.active,
            "on_clock": entry is not None,
            "clocked_in_at": entry.clocked_in_at if entry else None,
            "week_hours": employee_week(session, employee, None)["total_hours"],
            "status": employee_status(employee),
            "archived_at": employee.archived_at.isoformat() if employee.archived_at else None,
        }
        result.append(row)
    return result


def list_employees(session: Session, role: Optional[str] = None) -> List[Employee]:
    """
    Get list of active employees, sorted by name.
    
    Args:
        session: SQLAlchemy session
        role: Optional role filter
        
    Returns:
        List of active employees sorted by name
    """
    query = session.query(Employee).filter(Employee.active == True)
    
    if role is not None:
        query = query.filter(Employee.role == role)
        
    return query.order_by(Employee.name).all()


def on_clock(session: Session) -> List[dict]:
    """
    Get list of employees currently on clock.
    
    Returns:
        List of dictionaries with employee info for open time entries
    """
    # Get open time entries (clocked_out_at is NULL)
    open_entries = (
        session.query(TimeEntry)
        .filter(TimeEntry.clocked_out_at.is_(None))
        .all()
    )
    
    result = []
    for entry in open_entries:
        employee = session.get(Employee, entry.employee_id)
        if employee:  # This should always be true but checking for safety
            result.append({
                "employee_id": employee.id,
                "code": employee.code,
                "name": employee.name,
                "role": employee.role,
                "clocked_in_at": entry.clocked_in_at,
                "logged_in": entry.token_hash is not None,
            })
    
    return result


def force_clock_out(session: Session, employee_id: int) -> bool:
    """
    Force clock out an employee.
    
    Args:
        session: SQLAlchemy session
        employee_id: ID of the employee to clock out
        
    Returns:
        True if clocked out successfully
        
    Raises:
        ValueError: If employee is not on clock
    """
    # Find open time entry for this employee
    open_entry = (
        session.query(TimeEntry)
        .filter(
            TimeEntry.employee_id == employee_id,
            TimeEntry.clocked_out_at.is_(None)
        )
        .first()
    )
    
    if not open_entry:
        raise ValueError("Employee is not on clock")
    
    # Set clock out time
    open_entry.clocked_out_at = utcnow()
    session.commit()
    
    return True


class AdminError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


ROLE_PREFIX = {"admin": "ADM", "host": "HOST", "server": "SRV", "bartender": "BAR", "kitchen": "KIT"}


def next_code(session: Session, role: str) -> str:
    """The next employee code for a role, e.g. SRV5 after SRV4."""
    prefix = ROLE_PREFIX[role]
    numbers = [int(code[len(prefix):]) for (code,) in session.query(Employee.code).all()
               if code.startswith(prefix) and code[len(prefix):].isdigit()]
    return f"{prefix}{max(numbers, default=0) + 1}"


def add_employee(session: Session, data) -> Employee:
    """Add an employee. Positions keep the role order; the first one is the employee's main role."""
    positions = [role for role in ROLES if role in data.positions]
    code = next_code(session, positions[0])
    number = (session.query(func.max(Employee.number)).scalar() or 0) + 1
    employee = Employee(
        number=number,
        code=code,
        name=data.name.strip(),
        role=positions[0],
        positions=",".join(positions),
        address=data.address,
        dob=data.dob,
        hire_date=data.hire_date,
        ssn_last=code[len(ROLE_PREFIX[positions[0]]):],
        pin_hash=hash_pin(data.pin),
        location_id=1,
        active=True,
    )
    session.add(employee)
    session.commit()
    session.refresh(employee)
    return employee


def add_recipe(session: Session, data) -> MenuItem:
    """Add a menu item with its price and recipe. Its category decides which station it goes to."""
    if session.query(MenuItem).filter_by(name=data.name.strip()).first():
        raise AdminError(409, "A recipe with this name already exists")
    item = MenuItem(name=data.name.strip(), category=data.category, price_cents=data.price_cents, active=True)
    for line in data.ingredients:
        item.recipe_lines.append(RecipeLine(ingredient=line.ingredient.strip(), qty=line.qty, unit=line.unit.strip()))
    session.add(item)
    session.commit()
    session.refresh(item)
    return item

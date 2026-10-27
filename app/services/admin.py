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


def roster(session: Session) -> List[dict]:
    """Every employee with the oversight information: positions, on the clock, hours this week."""
    from app.services.timecard import employee_week
    rows = []
    for employee in session.query(Employee).order_by(Employee.name).all():
        entry = open_entry_for(session, employee.id)
        rows.append({
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
        })
    return rows


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


def list_recipes(session: Session) -> List[dict]:
    items = session.query(MenuItem).order_by(MenuItem.category, MenuItem.name).all()
    return [{
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "price_cents": item.price_cents,
        "ingredients": [{"ingredient": line.ingredient, "qty": line.qty, "unit": line.unit} for line in item.recipe_lines],
    } for item in items]

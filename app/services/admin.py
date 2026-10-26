from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.employee import Employee
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
                "clocked_in_at": entry.clocked_in_at
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
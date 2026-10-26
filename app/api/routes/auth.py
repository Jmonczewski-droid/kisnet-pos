from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.schemas.auth import ClockInIn, EmployeeOut, TokenOut, ClockedOutOut
from app.services.auth import clock_in, clock_out, AuthError, get_employee_by_token
from app.models.employee import Employee
from app.models.time_entry import TimeEntry


router = APIRouter()

@router.post("/clock-in", response_model=TokenOut)
def clock_in_endpoint(clock_in_data: ClockInIn, db: Session = Depends(get_db)):
    try:
        employee, token = clock_in(db, clock_in_data.code, clock_in_data.pin)
        return TokenOut(token=token, employee=EmployeeOut.model_validate(employee))
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/clock-out")
def clock_out_endpoint(authorization: str = Header(None), db: Session = Depends(get_db)):
    # Extract token
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    
    try:
        token = authorization.split(" ")[1]
    except (IndexError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization format")
    
    # Get employee by token
    employee = get_employee_by_token(db, token)
    
    if not employee:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
    # Check if employee has an open time entry
    time_entry = db.query(TimeEntry).filter_by(employee_id=employee.id, clocked_out_at=None).first()
    
    if not time_entry:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Employee not clocked in")
        
    try:
        # Perform clock out
        clock_out(db, employee)
        return ClockedOutOut(clocked_out=True)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.get("/me", response_model=EmployeeOut)
def get_me(authorization: str = Header(None), db: Session = Depends(get_db)):
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization header")
    
    try:
        token = authorization.split(" ")[1]
    except (IndexError, AttributeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization format")
    
    employee = get_employee_by_token(db, token)
    if not employee:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        
    return employee
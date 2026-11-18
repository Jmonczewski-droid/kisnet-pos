"""Look-in portal endpoints. View-only, apart from signing in and out and clocking an employee out."""
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models import Employee
from app.schemas.auth import ClockInIn
from app.services import lookin as service
from app.services.auth import AuthError

router = APIRouter()


def _token(authorization: str) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    return token if scheme == "Bearer" else ""


def current_viewer(db: Session = Depends(get_db), authorization: str = Header(None)) -> Employee:
    token = _token(authorization)
    viewer = service.viewer_for_token(db, token) if token else None
    if not viewer:
        raise HTTPException(status_code=401, detail="Sign in to the look-in portal")
    return viewer


@router.post("/lookin/login")
def lookin_login(data: ClockInIn, db: Session = Depends(get_db)):
    """Owner or manager signs in with code, PIN and authenticator code. No clock-in is needed."""
    try:
        employee, token = service.sign_in(db, data.code, data.pin, data.otp)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail,
                            headers={"X-Error-Code": e.code} if e.code else None)
    return {"token": token, "name": employee.name, "access": employee.access}


@router.get("/lookin")
def lookin_snapshot(_: Employee = Depends(current_viewer), db: Session = Depends(get_db)):
    """Today's sales, labor, open tickets and tables, and who is on the clock, as of right now."""
    return service.snapshot(db)


@router.post("/lookin/clock-out/{employee_id}")
def lookin_clock_out(employee_id: int, _: Employee = Depends(current_viewer), db: Session = Depends(get_db)):
    """Manage labor remotely: clock one employee out. The only thing the portal can change."""
    try:
        return service.clock_out(db, employee_id)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)


@router.post("/lookin/logout")
def lookin_logout(authorization: str = Header(None), db: Session = Depends(get_db)):
    token = _token(authorization)
    if token:
        service.sign_out(db, token)
    return {"signed_out": True}

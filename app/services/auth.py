from app.core.time import utcnow
from typing import Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from app.models.employee import Employee
from app.models.time_entry import TimeEntry
from datetime import timedelta
from app.core import totp
from app.core.constants import LOCKOUT_MINUTES, MAX_FAILED_ATTEMPTS
from app.core.security import hash_pin, verify_pin, new_token, hash_token
from fastapi import HTTPException, status


class SessionUser:
    """The signed-in person, acting in the role (position) of their current shift."""

    def __init__(self, employee: Employee, role: str):
        self._employee = employee
        self.role = role

    def __getattr__(self, name):
        return getattr(self._employee, name)


def employee_positions(employee: Employee) -> list:
    """The positions an employee can work; their role if none are listed."""
    return [p for p in (employee.positions or "").split(",") if p] or [employee.role]


class AuthError(Exception):
    """`code` is a short machine-readable reason the screens act on (sent as the X-Error-Code header)."""

    def __init__(self, status_code: int, detail: str, code: Optional[str] = None):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(detail)


def _check_not_locked(employee: Employee) -> None:
    if employee.locked_until and employee.locked_until > utcnow():
        minutes = max(1, int((employee.locked_until - utcnow()).total_seconds() // 60) + 1)
        raise AuthError(status.HTTP_429_TOO_MANY_REQUESTS,
                        f"Too many wrong attempts. Try again in {minutes} minute{'s' if minutes != 1 else ''}.",
                        code="locked")


def _record_failure(session: Session, employee: Employee) -> None:
    """Count a wrong PIN or code; lock the sign-in for a few minutes after too many in a row."""
    employee.failed_attempts = (employee.failed_attempts or 0) + 1
    if employee.failed_attempts >= MAX_FAILED_ATTEMPTS:
        employee.failed_attempts = 0
        employee.locked_until = utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
    session.commit()


def _record_success(session: Session, employee: Employee) -> None:
    if employee.failed_attempts or employee.locked_until:
        employee.failed_attempts = 0
        employee.locked_until = None
        session.commit()


def _verify_code_and_pin(session: Session, code: str, pin: str) -> Employee:
    """The active employee for code+PIN, or AuthError. Wrong PINs are counted toward a lockout."""
    employee = session.query(Employee).filter_by(code=code).first()

    if not employee:
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Invalid code or PIN")

    if not employee.active:
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Employee is inactive")

    _check_not_locked(employee)

    if not verify_pin(pin, employee.pin_hash):
        _record_failure(session, employee)
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Invalid code or PIN")

    return employee


def check_pin(session: Session, code: str, pin: str) -> Employee:
    """Return the active employee for code+PIN, or raise AuthError.

    A PIN the owner set is only good for choosing a new one: the employee must pick their own first.
    """
    employee = _verify_code_and_pin(session, code, pin)
    if employee.must_change_pin:
        raise AuthError(status.HTTP_403_FORBIDDEN, "Choose your own PIN before you sign in.",
                        code="pin_change_required")
    if not employee.totp_enabled:
        _record_success(session, employee)  # with two-step sign-in, only a correct code clears the count
    return employee


def change_pin(session: Session, code: str, pin: str, new_pin: str) -> Employee:
    """An employee replaces their PIN with one only they know."""
    employee = _verify_code_and_pin(session, code, pin)
    if new_pin == pin:
        raise AuthError(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose a PIN different from the current one")
    employee.pin_hash = hash_pin(new_pin)
    employee.must_change_pin = False
    employee.failed_attempts = 0
    employee.locked_until = None
    session.commit()
    return employee


def _check_otp(session: Session, employee: Employee, otp: Optional[str]) -> None:
    """Second step for an employee with an authenticator app: a current code, usable once."""
    if not otp:
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "Enter the code from your authenticator app.",
                        code="otp_required")
    step = totp.matching_step(employee.totp_secret, otp, after_step=employee.totp_last_step)
    if step is None:
        _record_failure(session, employee)
        raise AuthError(status.HTTP_401_UNAUTHORIZED, "That code is not correct, or has already been used.",
                        code="otp_invalid")
    employee.totp_last_step = step
    employee.failed_attempts = 0
    employee.locked_until = None
    session.commit()


def totp_status(employee: Employee) -> dict:
    return {"enabled": bool(employee.totp_enabled), "pending": bool(employee.totp_secret and not employee.totp_enabled)}


def totp_setup(session: Session, employee: Employee) -> dict:
    """Start two-step sign-in: a fresh key to load into an authenticator app. Not active until confirmed.

    For the owner and managers. It is required for the look-in portal.
    """
    if employee.access not in ("owner", "manager"):
        raise AuthError(status.HTTP_403_FORBIDDEN, "Two-step sign-in is for the owner and managers")
    if employee.totp_enabled:
        raise AuthError(status.HTTP_409_CONFLICT, "Two-step sign-in is already on. Turn it off first to set up a new device.")
    employee.totp_secret = totp.new_secret()
    employee.totp_last_step = None
    session.commit()
    uri = totp.provisioning_uri(employee.totp_secret, employee.code)
    return {"secret": employee.totp_secret, "uri": uri, "qr_svg": totp.qr_svg(uri)}


def totp_enable(session: Session, employee: Employee, otp: str) -> dict:
    """Confirm the app is set up by entering a code from it; two-step sign-in is on from then."""
    if employee.totp_enabled:
        raise AuthError(status.HTTP_409_CONFLICT, "Two-step sign-in is already on")
    if not employee.totp_secret:
        raise AuthError(status.HTTP_409_CONFLICT, "Start the setup first")
    step = totp.matching_step(employee.totp_secret, otp)
    if step is None:
        raise AuthError(status.HTTP_422_UNPROCESSABLE_ENTITY, "That code is not correct. Check the app and try again.")
    employee.totp_enabled = True
    employee.totp_last_step = step
    session.commit()
    return totp_status(employee)


def totp_disable(session: Session, employee: Employee, otp: str) -> dict:
    if not employee.totp_enabled:
        raise AuthError(status.HTTP_409_CONFLICT, "Two-step sign-in is not on")
    _check_otp(session, employee, otp)
    clear_totp(employee)
    session.commit()
    return totp_status(employee)


def clear_totp(employee: Employee) -> None:
    employee.totp_secret = None
    employee.totp_enabled = False
    employee.totp_last_step = None


def preview_clock_in(session: Session, code: str, pin: str) -> dict:
    """Who is signing in, their positions, and whether they are already on the clock (for the confirmation pop-up)."""
    employee = check_pin(session, code, pin)
    entry = open_entry_for(session, employee.id)
    return {"employee": employee, "positions": employee_positions(employee),
            "on_clock": entry is not None, "clocked_in_at": entry.clocked_in_at if entry else None}


def clock_in(session: Session, code: str, pin: str, position: Optional[str] = None) -> TimeEntry:
    """Start a shift in one of the employee's positions. Clocking in does not log anyone in."""
    employee = check_pin(session, code, pin)
    if open_entry_for(session, employee.id):
        raise AuthError(status.HTTP_409_CONFLICT, "Already clocked in")
    positions = employee_positions(employee)
    if position is None:
        if len(positions) > 1:
            raise AuthError(status.HTTP_422_UNPROCESSABLE_ENTITY, "Choose the position you are clocking in as")
        position = positions[0]
    if position not in positions:
        raise AuthError(status.HTTP_422_UNPROCESSABLE_ENTITY, "That position is not on this employee's list")
    entry = TimeEntry(employee_id=employee.id, clocked_in_at=utcnow(), token_hash=None, position=position)
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return entry


def login(session: Session, code: str, pin: str, otp: Optional[str] = None) -> Tuple[SessionUser, str]:
    """Open a station session in the position of the current shift. Only possible while on the clock.

    An employee with an authenticator app set up (the owner) must also give a current code.
    """
    employee = check_pin(session, code, pin)
    entry = open_entry_for(session, employee.id)
    if not entry:
        raise AuthError(status.HTTP_409_CONFLICT, "Not clocked in. Clock in first.")
    if employee.totp_enabled:
        _check_otp(session, employee, otp)
    token = new_token()
    entry.token_hash = hash_token(token)
    session.commit()
    return SessionUser(employee, entry.position or employee.role), token


def logout(session: Session, employee: Employee) -> None:
    """End this session but leave the employee on the clock."""
    entry = open_entry_for(session, employee.id)
    if entry:
        entry.token_hash = None
        session.commit()


def clock_out(session: Session, employee: Employee) -> None:
    # Find the open time entry for this employee
    time_entry = session.query(TimeEntry).filter_by(employee_id=employee.id, clocked_out_at=None).first()
    
    if not time_entry:
        raise AuthError(status.HTTP_409_CONFLICT, "Employee not clocked in")
        
    # Set clock out time
    time_entry.clocked_out_at = utcnow()
    
    session.commit()
    session.refresh(time_entry)


def get_employee_by_token(session: Session, token: str) -> Optional[SessionUser]:
    """The signed-in person for this token, in their shift's position, or None if the session is not active."""
    entry = session.query(TimeEntry).filter_by(token_hash=hash_token(token)).first()
    if not entry or entry.clocked_out_at:
        return None
    employee = session.get(Employee, entry.employee_id)
    return SessionUser(employee, entry.position or employee.role) if employee else None


def open_entry_for(session: Session, employee_id: int) -> Optional[TimeEntry]:
    """Get the currently open time entry for an employee"""
    return session.query(TimeEntry).filter_by(employee_id=employee_id, clocked_out_at=None).first()
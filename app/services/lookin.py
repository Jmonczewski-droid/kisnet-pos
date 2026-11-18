"""The look-in portal: a read-only, real-time view of today's business for the owner and managers.

It is the one part of the POS meant to be reached from outside the restaurant, so it is kept apart:
its own sign-in (no clock-in needed), its own short-lived token, and a feed that can only be read.
Nothing can be changed from the portal: no orders, no menu, no clock-outs.
"""
from datetime import timedelta
from typing import Optional, Tuple

from fastapi import status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_token, new_token
from app.core.time import utcnow
from app.models import Employee, Party, TimeEntry
from app.models.lookin import LookinSession
from app.services.auth import AuthError, _check_otp, check_pin
from app.services.stats import day_stats

LOOKIN_ACCESS = ("owner", "manager")


def sign_in(session: Session, code: str, pin: str, otp: Optional[str] = None) -> Tuple[Employee, str]:
    """Code + PIN + authenticator code -> a read-only look-in token. Returns (employee, token)."""
    employee = check_pin(session, code, pin)
    if employee.access not in LOOKIN_ACCESS:
        raise AuthError(status.HTTP_403_FORBIDDEN, "The look-in portal is for the owner and managers.")
    if employee.totp_enabled:
        _check_otp(session, employee, otp)
    elif settings.LOOKIN_REQUIRE_TWO_STEP:
        raise AuthError(status.HTTP_403_FORBIDDEN,
                        "Turn on two-step sign-in at the restaurant (Menu > Sign-in Security) before using the look-in portal.",
                        code="two_step_setup_required")

    now = utcnow()
    session.query(LookinSession).filter(LookinSession.expires_at <= now).delete()
    token = new_token()
    session.add(LookinSession(employee_id=employee.id, token_hash=hash_token(token), created_at=now,
                              expires_at=now + timedelta(hours=settings.LOOKIN_HOURS)))
    session.commit()
    return employee, token


def viewer_for_token(session: Session, token: str) -> Optional[Employee]:
    """The employee behind a look-in token, if it is current and they still have the access for it."""
    row = session.query(LookinSession).filter(LookinSession.token_hash == hash_token(token)).first()
    if not row or row.expires_at <= utcnow():
        return None
    employee = session.get(Employee, row.employee_id)
    if not employee or not employee.active or employee.archived_at is not None or employee.access not in LOOKIN_ACCESS:
        return None
    row.last_seen_at = utcnow()
    session.commit()
    return employee


def sign_out(session: Session, token: str) -> None:
    session.query(LookinSession).filter(LookinSession.token_hash == hash_token(token)).delete()
    session.commit()


def end_sessions_for(session: Session, employee_id: int) -> None:
    """Called when someone loses the access or has their sign-in reset. Does not commit."""
    session.query(LookinSession).filter(LookinSession.employee_id == employee_id).delete()


def snapshot(session: Session) -> dict:
    """Today's business right now. Numbers and who is working; no personal details."""
    stats = day_stats(session, None)
    entries = (session.query(TimeEntry).filter(TimeEntry.clocked_out_at.is_(None))
               .order_by(TimeEntry.clocked_in_at).all())
    on_clock = []
    for entry in entries:
        employee = session.get(Employee, entry.employee_id)
        if employee:
            tables = session.query(Party).filter(Party.server_id == employee.id, Party.closed_at.is_(None)).count()
            on_clock.append({"name": employee.name, "position": entry.position or employee.role,
                             "clocked_in_at": entry.clocked_in_at, "open_tables": tables})
    open_tables = session.query(Party).filter(Party.closed_at.is_(None)).count()
    return {
        "as_of": utcnow(),
        "date": stats["date"],
        "sales_cents": stats["sales_cents"],
        "labor_cents": stats["labor_cents"],
        "labor_pct": stats["labor_pct"],
        "active_tickets": stats["active_tickets"],
        "open_tables": open_tables,
        "on_clock": on_clock,
        "hours": stats["hours"],
    }

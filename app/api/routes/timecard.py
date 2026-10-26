from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_employee, require_roles
from app.db.base import get_db
from app.models import Employee
from app.services.timecard import employee_week, weekly_summary

router = APIRouter()


@router.get("/timecard")
def get_timecard(
    week: Optional[date] = Query(None, description="Any date in the week; defaults to this week"),
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    return employee_week(db, employee, week)


@router.get("/timecard/summary")
def get_timecard_summary(
    week: Optional[date] = Query(None, description="Any date in the week; defaults to this week"),
    _: Employee = Depends(require_roles("admin")),
    db: Session = Depends(get_db),
):
    return weekly_summary(db, week)

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import get_db, require_roles
from app.services.reports import daily_sales, food_usage
from app.services.daily_reports import day_summary, item_sales
from app.schemas.report import DailySalesOut, FoodUsageOut
from datetime import date


router = APIRouter()


@router.get("/reports/daily-sales", response_model=DailySalesOut)
def get_daily_sales(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    employee = Depends(require_roles("admin")),
):
    """Get daily sales report."""
    return daily_sales(db, start, end)


@router.get("/reports/food-usage", response_model=FoodUsageOut)
def get_food_usage(
    start: date | None = None,
    end: date | None = None,
    db: Session = Depends(get_db),
    employee = Depends(require_roles("admin")),
):
    """Get food usage report."""
    return food_usage(db, start, end)

@router.get("/reports/summary")
def get_day_summary(
    day: date | None = None,
    db: Session = Depends(get_db),
    employee = Depends(require_roles("admin")),
):
    """Total sales, number of tickets and average ticket for one business day (default today)."""
    return day_summary(db, day)


@router.get("/reports/items")
def get_item_sales(
    day: date | None = None,
    db: Session = Depends(get_db),
    employee = Depends(require_roles("admin")),
):
    """Items sold for one business day, most popular first, food and drink listed separately."""
    return item_sales(db, day)

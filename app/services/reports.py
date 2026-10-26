from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from app.core.config import settings
from app.models.order import Order, OrderItem, OrderItemIngredient


def resolve_range(start: date | None, end: date | None) -> Tuple[datetime, datetime]:
    """
    Convert local date range to naive UTC datetime range.
    
    Arguments:
        start: Start date (optional)
        end: End date (optional)
        
    Returns:
        Tuple of (start_datetime, end_datetime) as naive UTC datetimes
    """
    # Default to today in business timezone
    tz = ZoneInfo(settings.BUSINESS_TIMEZONE)
    today = datetime.now(tz).date()
    
    if start is None:
        start_date = today
    else:
        start_date = start
        
    if end is None:
        end_date = today
    else:
        end_date = end
    
    # Convert local dates to naive UTC datetimes - bounds are [start 00:00, end+1 00:00)
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.min.time()) + timedelta(days=1)
    
    # Convert to UTC
    start_utc = start_datetime.replace(tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    end_utc = end_datetime.replace(tzinfo=tz).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    
    return (start_utc, end_utc)


def daily_sales(session: Session, start: date | None, end: date | None) -> dict:
    """
    Calculate daily sales report for completed orders within the specified date range.
    
    Arguments:
        session: Database session
        start: Start date (optional)
        end: End date (optional)
        
    Returns:
        Dictionary with order_count, total_qty and rows of DailySalesRow objects
    """
    start_utc, end_utc = resolve_range(start, end)
    
    # Get completed orders within range (excluding voided items)
    completed_orders = session.query(Order).filter(
        and_(
            Order.completed_at >= start_utc,
            Order.completed_at < end_utc,
            Order.status == "completed"
        )
    ).all()
    
    # Group by item name and category (sum quantities)
    sales_data = {}
    
    for order in completed_orders:
        for item in order.items:
            # Skip voided items
            if item.voided:
                continue
                
            item_name = item.name
            item_category = item.category
            qty = item.qty
            
            key = (item_name, item_category)
            if key not in sales_data:
                sales_data[key] = {"qty": 0, "sales_cents": 0}
                
            sales_data[key]["qty"] += qty
            sales_data[key]["sales_cents"] += (item.unit_price_cents * qty)
    
    # Convert to list of DailySalesRow objects and sort by name
    rows = []
    for key in sorted(sales_data.keys()):
        name, category = key
        row = {
            "name": name,
            "category": category,
            "qty": sales_data[key]["qty"],
            "sales_cents": sales_data[key]["sales_cents"]
        }
        rows.append(row)
        
    return {
        "start": start or datetime.now(ZoneInfo(settings.BUSINESS_TIMEZONE)).date(),
        "end": end or datetime.now(ZoneInfo(settings.BUSINESS_TIMEZONE)).date(),
        "order_count": len(completed_orders),
        "total_qty": sum(row["qty"] for row in rows),
        "total_sales_cents": sum(row["sales_cents"] for row in rows),
        "rows": rows
    }


def food_usage(session: Session, start: date | None, end: date | None) -> dict:
    """
    Calculate food usage report for completed orders within the specified date range.
    
    Arguments:
        session: Database session
        start: Start date (optional)
        end: End date (optional)
        
    Returns:
        Dictionary with rows of FoodUsageRow objects
    """
    start_utc, end_utc = resolve_range(start, end)
    
    # Get all completed orders within the date range
    completed_orders = session.query(Order).filter(
        and_(
            Order.completed_at >= start_utc,
            Order.completed_at < end_utc,
            Order.status == "completed"
        )
    ).all()
    
    # Aggregate usage by ingredients
    usage_data = {}
    
    for order in completed_orders:
        for item in order.items:
            # Skip voided items
            if item.voided:
                continue
                
            for ingredient in item.ingredients:
                ing_name = ingredient.ingredient
                qty = ingredient.qty * item.qty  # Scale by quantity of the item purchased
                unit = ingredient.unit
                
                if ing_name not in usage_data:
                    usage_data[ing_name] = {"qty": 0, "unit": unit}
                
                usage_data[ing_name]["qty"] += qty
    
    # Convert to list of FoodUsageRow objects and sort by ingredient name
    rows = []
    for name in sorted(usage_data.keys()):
        row = {
            "ingredient": name,
            "unit": usage_data[name]["unit"],
            "qty": usage_data[name]["qty"]
        }
        rows.append(row)
        
    return {
        "start": start or datetime.now(ZoneInfo(settings.BUSINESS_TIMEZONE)).date(),
        "end": end or datetime.now(ZoneInfo(settings.BUSINESS_TIMEZONE)).date(),
        "rows": rows
    }
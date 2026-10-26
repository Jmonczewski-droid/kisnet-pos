from fastapi import APIRouter, Depends, Request, HTTPException, Response
from sqlalchemy.orm import Session
from typing import List

from app.api.deps import get_current_employee, get_db
from app.services.menu_import import import_menu, export_menu_csv
from app.models.menu import MenuItem
from app.core.constants import CATEGORIES


router = APIRouter()


@router.get("/menu")
async def get_menu(
    category: str | None = None,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
) -> List[dict]:
    """
    Get active menu items, optionally filtered by category.
    
    Args:
        category: Optional category filter
        db: Database session
        current_employee: Current authenticated employee
        
    Returns:
        List of active menu items sorted by name
    """
    # Build query for active menu items
    query = db.query(MenuItem).filter(MenuItem.active == True)
    
    if category is not None:
        if category not in CATEGORIES:
            raise HTTPException(status_code=422, detail="Invalid category")
        query = query.filter(MenuItem.category == category)
        
    # Get results and order by name
    items = query.order_by(MenuItem.name).all()
    
    # Return as list of dictionaries
    return [
        {
            "id": item.id,
            "name": item.name,
            "category": item.category,
            "price_cents": item.price_cents
        }
        for item in items
    ]


@router.get("/menu/export")
async def export_menu(
    response: Response,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
) -> str:
    """
    Export menu as CSV.
    
    Args:
        response: FastAPI response object to set content type
        db: Database session
        current_employee: Current authenticated employee
        
    Returns:
        CSV text with all recipe lines
        
    Raises:
        HTTPException: If user is not admin
    """
    # Check if user has admin role
    if current_employee.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Set content type header 
    response.headers["Content-Type"] = "text/csv"
    
    return export_menu_csv(db)


@router.post("/menu/import")
async def import_menu_route(
    request: Request,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
) -> dict:
    """
    Import menu from CSV.
    
    Args:
        request: FastAPI request object
        db: Database session
        current_employee: Current authenticated employee
        
    Returns:
        Dictionary with counts of imported items and recipe lines
        
    Raises:
        HTTPException: If user is not admin or CSV is invalid
    """
    # Check if user has admin role
    if current_employee.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Get raw body
    body = await request.body()
    text = body.decode("utf-8")
    
    try:
        items, recipe_lines = import_menu(db, text)
        return {"items": items, "recipe_lines": recipe_lines}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.services.parties import list_seats
from app.api.deps import get_current_employee

router = APIRouter()


@router.get("/seats")
def get_seats(
    db: Session = Depends(get_db),
    user=Depends(get_current_employee)
):
    """List all seats with their associated party information."""
    return list_seats(db, user)
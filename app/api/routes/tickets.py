from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.services.tickets import list_tickets, bump_ticket
from app.api.deps import get_current_employee


router = APIRouter()


@router.get("/tickets")
def get_tickets(track: str, db: Session = Depends(get_db), user = Depends(get_current_employee)):
    """
    Get tickets (open orders with items) for a specific track.
    
    Response format:
        List of ticket dictionaries containing order_id, track, seat, party_name, opened_at, items
        Items are filtered by category == track and bumped_at IS NULL
        Only open orders are included
        Sorted by opened_at (oldest first)
    """
    return list_tickets(db, user, track)


@router.post("/tickets/{order_id}/{track}/bump")
def bump_order_ticket(order_id: int, track: str, db: Session = Depends(get_db), user = Depends(get_current_employee)):
    """
    Bump items from a specific track for an order.
    
    Returns:
        int: Count of items that were bumped
    """
    return bump_ticket(db, user, order_id, track)
from typing import List, Dict
from sqlalchemy.orm import Session
from app.models import Order, OrderItem, Party
from app.services.orders import item_out
from app.core.time import utcnow
from fastapi import HTTPException
from app.core.constants import CATEGORIES, TRACKS


def ticket_access(user, track: str) -> None:
    """
    Check if user can access items for a given track.
    
    Raises:
        HTTPException(403): If role may not see the track
        HTTPException(422): If invalid track
    """
    # Validate track
    if track not in TRACKS:
        raise HTTPException(status_code=422, detail="Invalid track")
    
    # Check access based on role and track
    if user.role == "admin":
        return  # Admin can see all tracks
    elif user.role == "host" or user.role == "server":
        raise HTTPException(status_code=403, detail="Not authorized to view tickets")
    elif user.role == "bartender":
        if track != "bar":
            raise HTTPException(status_code=403, detail="Bartender may only view bar items")
    elif user.role == "kitchen":
        if track not in ("appetizers", "hot", "cold"):
            raise HTTPException(status_code=403, detail="Kitchen may only view appetizers, hot, or cold items")
    # admin and host/server roles already handled


def list_tickets(session: Session, user, track: str) -> List[Dict]:
    """
    List open orders with items matching the given track.
    
    Returns:
        List of dictionaries containing order_id, track, seat, party_name, opened_at, items
        Items are filtered by category == track and bumped_at IS NULL
        Only open orders are included
        Sorted by opened_at (oldest first)
    """
    # Validate access
    ticket_access(user, track)
    
    tickets = []
    
    # Get all open orders with related info
    open_orders = session.query(Order).filter_by(status="open").join(Party).all()
    
    for order in open_orders:
        # Filter items for the specific track and not bumped
        matching_items = [item for item in order.items 
                         if item.category == track and item.bumped_at is None]
        
        if matching_items:  # Only include orders with items for this track
            ticket = {
                "order_id": order.id,
                "track": track,
                "seat": order.party.seat,
                "party_id": order.party.id,
                "party_name": order.party.party_name,
                "opened_at": min(item.sent_at for item in matching_items),
                "items": [item_out(item) for item in matching_items],
            }
            tickets.append(ticket)
    
    # Sort by opened_at (oldest first)
    tickets.sort(key=lambda x: x["opened_at"])
    
    return tickets


def bump_ticket(session: Session, user, order_id: int, track: str) -> int:
    """
    Bump items from a specific track for an order.
    
    Returns:
        int: Count of items bumped
        
    Raises:
        HTTPException(404): If order not found
    """
    # Validate access
    ticket_access(user, track)
    
    # Get the order
    order = session.get(Order, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Filter items for the specific track and not bumped yet
    items_to_bump = [item for item in order.items 
                     if item.category == track and item.bumped_at is None]
    
    # Set bumped_at for each item
    count = 0
    for item in items_to_bump:
        item.bumped_at = utcnow()
        count += 1
    
    session.commit()
    return count
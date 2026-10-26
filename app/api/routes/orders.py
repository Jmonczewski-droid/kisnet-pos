from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.api.deps import get_current_employee, get_db
from app.services.orders import (
    add_items,
    send_ticket,
    update_item,
    void_item,
    complete_order,
    order_out,
    OrderError
)
from app.schemas.order import OrderOut, OrderItemsIn, OrderItemPatch, TicketSendIn
from app.models import Party, OrderItem

router = APIRouter()


@router.post("/parties/{party_id}/send", response_model=OrderOut)
async def send_order_ticket(
    party_id: int,
    ticket: TicketSendIn,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
):
    """Send the ticket: new lines, changes and voids are saved and go to the kitchen and bar."""
    party = db.get(Party, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    try:
        order = send_ticket(db, current_employee, party, ticket.items, ticket.updates, ticket.voids)
        return order_out(order)
    except OrderError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@router.post("/parties/{party_id}/items", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def add_order_items(
    party_id: int,
    items: OrderItemsIn,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
):
    """Add items to an order for a party."""
    # Get the party
    party = db.get(Party, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    
    try:
        order = add_items(db, current_employee, party, items)
        return order_out(order)
    except OrderError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@router.patch("/order-items/{item_id}", response_model=OrderOut)
async def update_order_item(
    item_id: int,
    patch: OrderItemPatch,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
):
    """Update an existing order item."""
    # Get the item
    item = db.get(OrderItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found")
    
    try:
        updated_item = update_item(db, current_employee, item, patch)
        # Reload the order to return complete updated order
        order = db.get(Party, item.order.party_id).orders[0]  # Get relevant order
        return order_out(order)
    except OrderError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@router.delete("/order-items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def void_order_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
):
    """Void an existing order item."""
    # Get the item
    item = db.get(OrderItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Order item not found")
    
    try:
        void_item(db, current_employee, item)
        return None
    except OrderError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@router.post("/parties/{party_id}/complete", response_model=OrderOut)
async def complete_order_party(
    party_id: int,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
):
    """Complete the open order for a party."""
    # Get the party
    party = db.get(Party, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    
    try:
        completed_order = complete_order(db, current_employee, party)
        return order_out(completed_order)
    except OrderError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)
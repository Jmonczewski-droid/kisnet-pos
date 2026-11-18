from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
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
from app.models import Order, Party, OrderItem
from app.services.devices import print_order_lines

router = APIRouter()


def _open_item_ids(db: Session, party_id: int) -> set:
    """Ids of the lines already on the party's open order (to tell which lines a send adds)."""
    order = db.query(Order).filter_by(party_id=party_id, status="open").first()
    return {item.id for item in order.items} if order else set()


@router.post("/parties/{party_id}/send", response_model=OrderOut)
async def send_order_ticket(
    party_id: int,
    ticket: TicketSendIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
):
    """Send the ticket: new lines, changes and voids are saved and go to the kitchen and bar."""
    party = db.get(Party, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    try:
        before = _open_item_ids(db, party_id)
        order = send_ticket(db, current_employee, party, ticket.items, ticket.updates, ticket.voids)
        # Print only what this send touched: new lines, changed lines and voids
        touched = ([item.id for item in order.items if item.id not in before]
                   + [update.item_id for update in ticket.updates] + list(ticket.voids))
        background.add_task(print_order_lines, order.id, touched)
        return order_out(order)
    except OrderError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@router.post("/parties/{party_id}/items", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def add_order_items(
    party_id: int,
    items: OrderItemsIn,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    current_employee = Depends(get_current_employee)
):
    """Add items to an order for a party."""
    # Get the party
    party = db.get(Party, party_id)
    if not party:
        raise HTTPException(status_code=404, detail="Party not found")
    
    try:
        before = _open_item_ids(db, party_id)
        order = add_items(db, current_employee, party, items)
        background.add_task(print_order_lines, order.id, [item.id for item in order.items if item.id not in before])
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
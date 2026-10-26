from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import Order, OrderItem, Party, MenuItem
from app.schemas.order import OrderOut, OrderItemOut, OrderItemsIn, OrderItemPatch
from app.core.time import utcnow
from fastapi import HTTPException


class OrderError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def can_order(user, party) -> bool:
    """Check if user can add items to this party."""
    if user.role == "admin":
        return True
    if user.role == "server":
        return party.server_id == user.id
    if user.role == "bartender":
        from app.core.constants import BAR_SEATS
        return party.seat in BAR_SEATS
    return False


def can_view_party(user, party) -> bool:
    """Check if user can view this party."""
    if user.role == "admin" or user.role == "host":
        return True
    if user.role == "server":
        return party.server_id == user.id
    if user.role == "bartender":
        from app.core.constants import BAR_SEATS
        return party.seat in BAR_SEATS
    return False


def _ensure_party_open(session: Session, party_id: int) -> Party:
    """Ensure party exists and is open."""
    party = session.get(Party, party_id)
    if not party:
        raise OrderError(404, "Party not found")
    if party.closed_at is not None:
        raise OrderError(409, "Party is closed")
    return party


def _ensure_party_exists(session: Session, party_id: int) -> Party:
    """Ensure party exists."""
    party = session.get(Party, party_id)
    if not party:
        raise OrderError(404, "Party not found")
    return party


def _ensure_item_exists(session: Session, item_id: int) -> OrderItem:
    """Ensure order item exists."""
    item = session.get(OrderItem, item_id)
    if not item:
        raise OrderError(404, "Order item not found")
    return item


def add_items(session: Session, user, party, items: OrderItemsIn) -> Order:
    """Add items to an existing or new order for the party."""
    # Ensure party is open
    party = _ensure_party_open(session, party.id)
    
    # Check permissions
    if not can_order(user, party):
        raise OrderError(403, "Not authorized to add items to this party")
    
    # Get or create order
    order = None
    for o in party.orders:
        if o.status == "open":
            order = o
            break
    
    if not order:
        # Create new order
        order = Order(
            party_id=party.id,
            status="open",
            opened_at=utcnow()
        )
        session.add(order)
        session.flush()  # Ensure we have an ID for the new order
    else:
        # Make sure this is not a completed order
        if order.status == "completed":
            raise OrderError(409, "Party has a completed order")
    
    # Process items
    already_has_items = len(order.items) > 0
    changed = already_has_items
    
    for item_data in items.items:
        # Verify menu item exists and is active
        menu_item = session.get(MenuItem, item_data.menu_item_id)
        if not menu_item or not menu_item.active:
            raise OrderError(422, "Invalid menu item")
        
        # Create order item
        order_item = OrderItem(
            order_id=order.id,
            menu_item_id=item_data.menu_item_id,
            name=menu_item.name,
            category=menu_item.category,
            unit_price_cents=menu_item.price_cents,
            qty=item_data.qty,
            notes=item_data.notes,
            changed=changed,
            created_by_id=user.id,
            sent_at=utcnow(),
        )
        
        session.add(order_item)
        session.flush()  # assign order_item.id before copying recipe lines
        
        # Copy recipe lines to order_item_ingredients
        for recipe_line in menu_item.recipe_lines:
            from app.models import OrderItemIngredient
            ingredient = OrderItemIngredient(
                order_item_id=order_item.id,
                ingredient=recipe_line.ingredient,
                qty=recipe_line.qty,
                unit=recipe_line.unit
            )
            session.add(ingredient)
    
    session.commit()
    
    # Reload order to get the updated items
    session.refresh(order)
    
    return order


def update_item(session: Session, user, item: OrderItem, patch: OrderItemPatch) -> OrderItem:
    """Update an existing order item."""
    # Verify the item exists and is not voided or bumped
    if item.voided:
        raise OrderError(409, "Cannot modify a voided item")
    if item.bumped_at:
        raise OrderError(409, "Cannot modify a bumped item")
    
    # Check permissions
    party = _ensure_party_exists(session, item.order.party_id)
    if not can_order(user, party):
        raise OrderError(403, "Not authorized to modify items in this party")
    
    # Update item fields
    if patch.qty is not None:
        item.qty = patch.qty
        item.changed = True
    
    if patch.notes is not None:
        item.notes = patch.notes
    
    session.commit()
    session.refresh(item)
    
    return item


def void_item(session: Session, user, item: OrderItem) -> None:
    """Void an existing order item."""
    # Verify the item exists and is not already voided or bumped
    if item.voided:
        raise OrderError(409, "Item is already voided")
    if item.bumped_at:
        raise OrderError(409, "Cannot void a bumped item")
    
    # Check permissions
    party = _ensure_party_exists(session, item.order.party_id)
    if not can_order(user, party):
        raise OrderError(403, "Not authorized to modify items in this party")
    
    item.voided = True
    session.commit()


def complete_order(session: Session, user, party) -> Order:
    """Complete the open order for a party."""
    # Ensure party exists
    party = _ensure_party_exists(session, party.id)
    
    # Check permissions
    if not can_order(user, party):
        raise OrderError(403, "Not authorized to complete this party's order")
    
    # Find the open order
    order = None
    for o in party.orders:
        if o.status == "open":
            order = o
            break
    
    if not order:
        raise OrderError(409, "No open order for this party")
    
    order.status = "completed"
    order.completed_at = utcnow()
    session.commit()
    
    return order


def item_out(item: OrderItem) -> OrderItemOut:
    """Build the API shape for one order line, including computed fields."""
    return OrderItemOut(
        id=item.id,
        menu_item_id=item.menu_item_id,
        name=item.name,
        category=item.category,
        unit_price_cents=item.unit_price_cents,
        qty=item.qty,
        notes=item.notes,
        changed=item.changed,
        voided=item.voided,
        bumped=item.bumped_at is not None,
        sent_at=item.sent_at,
        line_total_cents=0 if item.voided else item.unit_price_cents * item.qty,
    )


def order_out(order: Order) -> OrderOut:
    """Build the API shape for an order, with total_cents over non-voided lines."""
    items_out = [item_out(item) for item in order.items]
    return OrderOut(
        id=order.id,
        party_id=order.party_id,
        status=order.status,
        opened_at=order.opened_at,
        completed_at=order.completed_at,
        total_cents=sum(line.line_total_cents for line in items_out),
        items=items_out,
    )
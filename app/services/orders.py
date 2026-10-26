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


def _open_order(session: Session, party) -> Optional[Order]:
    return session.query(Order).filter_by(party_id=party.id, status="open").first()


def _append_items(session: Session, user, order: Order, lines, changed: bool) -> None:
    """Add order lines (with recipe snapshots) to an order. Does not commit."""
    from app.models import OrderItemIngredient
    for item_data in lines:
        menu_item = session.get(MenuItem, item_data.menu_item_id)
        if not menu_item or not menu_item.active:
            raise OrderError(422, "Invalid menu item")

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

        for recipe_line in menu_item.recipe_lines:
            session.add(OrderItemIngredient(
                order_item_id=order_item.id,
                ingredient=recipe_line.ingredient,
                qty=recipe_line.qty,
                unit=recipe_line.unit
            ))


def add_items(session: Session, user, party, items: OrderItemsIn) -> Order:
    """Add items to the party's open order (creating it if needed)."""
    party = _ensure_party_open(session, party.id)
    if not can_order(user, party):
        raise OrderError(403, "Not authorized to add items to this party")

    order = _open_order(session, party)
    if not order:
        order = Order(party_id=party.id, status="open", opened_at=utcnow())
        session.add(order)
        session.flush()

    # Lines added after the first send are marked CHANGED on the kitchen ticket
    changed = len(order.items) > 0
    _append_items(session, user, order, items.items, changed)
    session.commit()
    session.refresh(order)
    return order


def send_ticket(session: Session, user, party, new_items, updates, voids) -> Order:
    """
    Send the ticket in one step: new lines, quantity/note changes to sent lines,
    and voids. Nothing is saved until this is called.
    """
    party = _ensure_party_open(session, party.id)
    if not can_order(user, party):
        raise OrderError(403, "Not authorized to send items for this party")

    order = _open_order(session, party)
    if order is None and (updates or voids):
        raise OrderError(409, "No open order to change")

    # Check every change against the order before touching anything
    existing = {item.id: item for item in order.items} if order else {}
    for update in updates:
        item = existing.get(update.item_id)
        if item is None:
            raise OrderError(422, f"Item {update.item_id} is not on this ticket")
        if item.voided or item.bumped_at:
            raise OrderError(409, f"{item.name} has already gone to the kitchen or bar")
    for item_id in voids:
        item = existing.get(item_id)
        if item is None:
            raise OrderError(422, f"Item {item_id} is not on this ticket")
        if item.voided or item.bumped_at:
            raise OrderError(409, f"{item.name} has already gone to the kitchen or bar")

    if not new_items and not updates and not voids:
        raise OrderError(422, "Nothing to send")

    if order is None:
        order = Order(party_id=party.id, status="open", opened_at=utcnow())
        session.add(order)
        session.flush()

    for update in updates:
        item = existing[update.item_id]
        if update.qty is not None and update.qty != item.qty:
            item.qty = update.qty
            item.changed = True
        if update.notes is not None:
            item.notes = update.notes

    for item_id in voids:
        existing[item_id].voided = True

    changed = len(order.items) > 0
    _append_items(session, user, order, new_items, changed)
    session.commit()
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
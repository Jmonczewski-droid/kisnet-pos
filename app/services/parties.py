from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models import Party, Employee
from app.schemas.party import PartySummary, PartyDetail
from app.schemas.order import OrderOut
from app.services.orders import can_order, can_view_party, order_out
from app.core.time import utcnow
from app.core.constants import ALL_SEATS, TABLE_SEATS, BAR_SEATS
from fastapi import HTTPException


class PartyError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(detail)


def _drinks_ready_at(session: Session, party) -> Optional[str]:
    """Latest time the bar bumped a drink on this party's open order (ISO), or None."""
    from sqlalchemy import func
    from app.models import Order, OrderItem
    latest = (
        session.query(func.max(OrderItem.bumped_at))
        .join(Order, OrderItem.order_id == Order.id)
        .filter(Order.party_id == party.id, Order.status == "open",
                OrderItem.category == "bar", OrderItem.voided == False)  # noqa: E712
        .scalar()
    )
    return latest.isoformat() if latest else None


def list_seats(session: Session, user) -> List[dict]:
    """List all seats with their party information."""
    # Get all open parties for filtering
    open_parties = session.execute(
        select(Party).where(Party.closed_at.is_(None))
    ).scalars().all()
    
    seat_dict = {}
    for seat in ALL_SEATS:
        seat_dict[seat] = {"seat": seat, "party": None}
    
    # Create PartySummary objects for visible parties
    for party in open_parties:
        if can_view_party(user, party):
            # Need to get server name for the summary
            server_name = None
            if party.server_id:
                server = session.get(Employee, party.server_id)
                if server:
                    server_name = server.name
            
            party_summary = PartySummary(
                id=party.id,
                seat=party.seat,
                party_name=party.party_name,
                party_size=party.party_size,
                drinks_ready_at=_drinks_ready_at(session, party),
                server_id=party.server_id,
                server_name=server_name,
                opened_at=party.opened_at.isoformat() if party.opened_at else None
            )
            
            seat_dict[party.seat]["party"] = party_summary
    
    # Return the list in ALL_SEATS order
    result = []
    for seat in ALL_SEATS:
        result.append(seat_dict[seat])
    
    return result


def list_open_parties(session: Session, user) -> List[PartySummary]:
    """List open parties that the user can view."""
    # Get all open parties
    open_parties_query = select(Party).where(Party.closed_at.is_(None))
    open_parties = session.execute(open_parties_query).scalars().all()
    
    # Filter parties by access rules
    visible_parties = []
    for party in open_parties:
        if can_view_party(user, party):
            server_name = None
            if party.server_id:
                server = session.get(Employee, party.server_id)
                if server:
                    server_name = server.name
            
            party_summary = PartySummary(
                id=party.id,
                seat=party.seat,
                party_name=party.party_name,
                party_size=party.party_size,
                drinks_ready_at=_drinks_ready_at(session, party),
                server_id=party.server_id,
                server_name=server_name,
                opened_at=party.opened_at.isoformat() if party.opened_at else None
            )
            
            visible_parties.append(party_summary)
    
    return visible_parties


def create_party(session: Session, user, data) -> PartyDetail:
    """Create a new party."""
    from app.db.base import Base
    
    # Check seat validity
    if data.seat not in ALL_SEATS:
        raise PartyError(422, "Invalid seat code")
    
    # Check user role is allowed to create parties at this seat
    if user.role not in ("host", "bartender", "admin"):
        raise PartyError(403, "Not authorized to create a party at this location")
    
    # For host role, verify it's a table seat
    if user.role == "host" and data.seat not in TABLE_SEATS:
        raise PartyError(403, "Hosts can only create parties at table seats")
    
    # For bartender role, verify it's a bar seat
    if user.role == "bartender" and data.seat not in BAR_SEATS:
        raise PartyError(403, "Bartenders can only create parties at bar seats")
    
    # Check if seat already has an open party
    existing_party = session.execute(
        select(Party).where(
            Party.seat == data.seat,
            Party.closed_at.is_(None)
        )
    ).scalar()
    
    if existing_party:
        raise PartyError(409, "Seat is already occupied")
    
    # Table parties need a size; bar parties do not (the bartender is the server)
    if data.seat in TABLE_SEATS and not data.party_size:
        raise PartyError(422, "Party size is required at tables")

    # For host role, ensure server_id is valid
    if user.role == "host":
        if not data.server_id:
            raise PartyError(422, "Server ID is required for table parties")
        
        # Check that the server exists and is active
        server = session.get(Employee, data.server_id)
        if not server or not server.active:
            raise PartyError(422, "Invalid server")
    
    # Create the party
    party = Party(
        seat=data.seat,
        party_name=data.party_name,
        party_size=data.party_size or 1,
        server_id=user.id if user.role == "bartender" else data.server_id,
        created_by_id=user.id,
        opened_at=utcnow()
    )
    
    session.add(party)
    session.commit()
    session.refresh(party)
    
    # Return party details
    return get_party_detail(session, user, party.id)


def get_party_detail(session: Session, user, party_id: int) -> PartyDetail:
    """Get detailed information for a specific party."""
    party = session.get(Party, party_id)
    if not party:
        raise PartyError(404, "Party not found")
    
    if not can_view_party(user, party):
        raise PartyError(403, "Not authorized to view this party")
    
    # Get open order if exists
    open_order = None
    for order in party.orders:
        if order.status == "open":
            open_order = order_out(order)
            break
    
    # Get server name if exists
    server_name = None
    if party.server_id:
        server = session.get(Employee, party.server_id)
        if server:
            server_name = server.name
    
    return PartyDetail(
        id=party.id,
        seat=party.seat,
        party_name=party.party_name,
        party_size=party.party_size,
        drinks_ready_at=_drinks_ready_at(session, party),
        server_id=party.server_id,
        server_name=server_name,
        opened_at=party.opened_at.isoformat() if party.opened_at else None,
        closed_at=party.closed_at.isoformat() if party.closed_at else None,
        open_order=open_order
    )


def close_party(session: Session, user, party_id: int) -> PartyDetail:
    """Close an existing party."""
    party = session.get(Party, party_id)
    if not party:
        raise PartyError(404, "Party not found")
    
    if party.closed_at is not None:
        raise PartyError(409, "Party is already closed")
    
    # Closing the table completes its open order (sent items stay on the report)
    for order in party.orders:
        if order.status == "open":
            order.status = "completed"
            order.completed_at = utcnow()
    
    # Servers send their own tables to payment (closing the table completes its order)
    if user.role == "server":
        if party.server_id != user.id or party.seat not in TABLE_SEATS:
            raise PartyError(403, "Servers can only send their own tables to payment")
    
    # For host or bartender or admin, check seat permissions
    if user.role == "host" and party.seat not in TABLE_SEATS:
        raise PartyError(403, "Hosts can only close parties at table seats")
    
    if user.role == "bartender" and party.seat not in BAR_SEATS:
        raise PartyError(403, "Bartenders can only close parties at bar seats")
    
    # Close the party
    party.closed_at = utcnow()
    session.commit()
    session.refresh(party)
    
    # Return updated party details
    return get_party_detail(session, user, party.id)
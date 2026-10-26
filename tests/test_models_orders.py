import tempfile
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.models import Employee, Party, Order, OrderItem, OrderItemIngredient
from app.core.time import utcnow


def test_order_models():
    # Create in-memory SQLite engine
    tmpdir = tempfile.mkdtemp()
    db_url = f"sqlite:///{tmpdir}/test.db"
    
    # Create engine and session
    engine = create_engine(db_url, echo=False)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    # Create session
    db = SessionLocal()
    
    try:
        # Insert an Employee first (required for relationships)
        employee = Employee(
            id=1,
            location_id=1,
            number=1,
            code="SRV1",
            name="Michael Brooks", 
            role="server",
            pin_hash="pbkdf2_sha256$200000$salt$hash",
            active=True
        )
        db.add(employee)
        db.commit()
        db.refresh(employee)
        
        # Create a Party with a server
        party = Party(
            id=1,
            location_id=1,
            seat="B2",
            party_name="Test Party",
            party_size=4,
            server_id=1,  # This references the employee we just created
            created_by_id=1,
            opened_at=utcnow(),
            closed_at=None
        )
        db.add(party)
        db.commit()
        db.refresh(party)
        
        # Create an Order with two OrderItems (one with an OrderItemIngredient)  
        order = Order(
            id=1,
            location_id=1,
            party_id=1,  # References the party we just created
            status="open",
            opened_at=utcnow(),
            completed_at=None
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        
        # Create first OrderItem (without ingredients)
        order_item_1 = OrderItem(
            id=1,
            order_id=1,
            menu_item_id=None,  # This will be null for a custom item
            name="Custom Item", 
            category="appetizers",
            unit_price_cents=1500,  # $15.00
            qty=2,
            notes="Special request",
            changed=True,
            voided=False,
            created_by_id=1,
            sent_at=utcnow(),
            bumped_at=None
        )
        db.add(order_item_1)
        db.commit()
        db.refresh(order_item_1)
        
        # Create second OrderItem (with ingredients)
        order_item_2 = OrderItem(
            id=2,
            order_id=1,
            menu_item_id=1,  # Reference to a menu item (we'll assume id=1 exists from seeding)
            name="Burger",
            category="hot",
            unit_price_cents=2500,  # $25.00
            qty=1,
            notes=None,
            changed=False,
            voided=False,
            created_by_id=1,
            sent_at=utcnow(),
            bumped_at=None
        )
        db.add(order_item_2)
        db.commit()
        db.refresh(order_item_2)
        
        # Create OrderItemIngredient for the second OrderItem
        order_item_ing = OrderItemIngredient(
            id=1,
            order_item_id=2,
            ingredient="Ground Beef",
            qty=0.5,
            unit="lbs"
        )
        db.add(order_item_ing)
        db.commit()
        db.refresh(order_item_ing)
        
        # Query back and assert values
        retrieved_order = db.query(Order).filter(Order.id == 1).first()
        assert retrieved_order.id == 1
        assert retrieved_order.party_id == 1
        assert retrieved_order.status == "open"
        assert retrieved_order.opened_at is not None
        
        # Verify order items ordering by id
        assert len(retrieved_order.items) == 2
        assert retrieved_order.items[0].id == 1  # First item added
        assert retrieved_order.items[1].id == 2  # Second item added
        
        # Verify the first item values
        assert retrieved_order.items[0].name == "Custom Item"
        assert retrieved_order.items[0].qty == 2
        assert retrieved_order.items[0].notes == "Special request"
        
        # Verify the second item values  
        assert retrieved_order.items[1].name == "Burger"
        assert retrieved_order.items[1].qty == 1
        assert retrieved_order.items[1].category == "hot"
        
        # Verify relationship through party
        retrieved_party = db.query(Party).filter(Party.id == 1).first()
        assert len(retrieved_party.orders) == 1
        assert retrieved_party.orders[0].id == 1
        
        # Verify second order item ingredients
        assert len(retrieved_order.items[1].ingredients) == 1
        assert retrieved_order.items[1].ingredients[0].ingredient == "Ground Beef"
        assert retrieved_order.items[1].ingredients[0].qty == 0.5
        assert retrieved_order.items[1].ingredients[0].unit == "lbs"
        
    finally:
        db.close()
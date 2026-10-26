import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db.base import Base
from app.models import Employee, TimeEntry, MenuItem, RecipeLine


def test_models():
    # Create an in-memory SQLite engine
    engine = create_engine("sqlite://")
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    # Create a session
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    
    try:
        # Insert an Employee
        employee = Employee(
            location_id=1,
            number=1,
            code="EMP001",
            name="John Doe",
            role="server",
            pin_hash="hashed_pin",
            active=True
        )
        session.add(employee)
        session.commit()
        session.refresh(employee)
        
        # Insert a TimeEntry
        time_entry = TimeEntry(
            employee_id=employee.id,
            clocked_in_at=datetime(2023, 1, 1, 10, 0, 0),
            clocked_out_at=None,
            token_hash="token_hash"
        )
        session.add(time_entry)
        session.commit()
        session.refresh(time_entry)
        
        # Insert a MenuItem with two RecipeLines
        menu_item = MenuItem(
            name="Cheeseburger",
            category="hot",
            price_cents=1200,  # $12.00
            active=True
        )
        session.add(menu_item)
        session.commit()
        session.refresh(menu_item)
        
        # Add two RecipeLines
        recipe_line_1 = RecipeLine(
            menu_item_id=menu_item.id,
            ingredient="beef_patty",
            qty=1.0,
            unit="lb"
        )
        recipe_line_2 = RecipeLine(
            menu_item_id=menu_item.id,
            ingredient="cheese_slice",
            qty=2.0,
            unit="slices"
        )
        
        session.add(recipe_line_1)
        session.add(recipe_line_2)
        session.commit()
        
        # Query back the data
        retrieved_employee = session.query(Employee).filter(Employee.id == employee.id).first()
        assert retrieved_employee.name == "John Doe"
        assert retrieved_employee.role == "server"
        
        retrieved_time_entry = session.query(TimeEntry).filter(TimeEntry.id == time_entry.id).first()
        assert retrieved_time_entry.employee_id == employee.id
        assert retrieved_time_entry.clocked_in_at is not None
        
        retrieved_menu_item = session.query(MenuItem).filter(MenuItem.id == menu_item.id).first()
        assert retrieved_menu_item.name == "Cheeseburger"
        assert retrieved_menu_item.category == "hot"
        assert retrieved_menu_item.price_cents == 1200
        
        # Check that the menu item has the two recipe lines
        assert len(retrieved_menu_item.recipe_lines) == 2
        recipe_line_names = [rl.ingredient for rl in retrieved_menu_item.recipe_lines]
        assert "beef_patty" in recipe_line_names
        assert "cheese_slice" in recipe_line_names
        
        # Test cascading delete - Delete the menu item and verify recipe lines are deleted too
        session.delete(retrieved_menu_item)
        session.commit()
        
        # Verify that the menu item was deleted
        deleted_menu_item = session.query(MenuItem).filter(MenuItem.id == menu_item.id).first()
        assert deleted_menu_item is None
        
        # Verify that the recipe lines were also deleted (cascade delete)
        deleted_recipe_lines = session.query(RecipeLine).filter(RecipeLine.menu_item_id == menu_item.id).all()
        assert len(deleted_recipe_lines) == 0
        
    finally:
        session.close()
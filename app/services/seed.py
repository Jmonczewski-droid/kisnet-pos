import os
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.employee import Employee
from app.models.menu import MenuItem
from app.services.menu_import import import_menu
from app.core.security import hash_pin


def seed_all(session: Session):
    """
    Idempotent seeding of employees and menu.
    
    Args:
        session: SQLAlchemy session
    """
    # Seed employees if table is empty
    employee_count = session.query(Employee).count()
    if employee_count == 0:
        # Create seed employees with PIN "1234" 
        employees_data = [
            {"number": 1, "code": "HOST1", "name": "Emma Carter", "role": "host"},
            {"number": 2, "code": "SRV1", "name": "Michael Brooks", "role": "server"},
            {"number": 3, "code": "KIT1", "name": "Carlos Diaz", "role": "kitchen"},
            {"number": 4, "code": "BAR1", "name": "Jessica Moore", "role": "bartender"},
            {"number": 5, "code": "ADM1", "name": "Linda Park", "role": "admin"}
        ]
        
        for emp_data in employees_data:
            employee = Employee(
                number=emp_data["number"],
                code=emp_data["code"], 
                name=emp_data["name"],
                role=emp_data["role"],
                pin_hash=hash_pin("1234"),
                location_id=1,
                active=True
            )
            session.add(employee)
    
    # Seed menu if table is empty
    menu_item_count = session.query(MenuItem).count()
    if menu_item_count == 0:
        # Read and import the seed menu CSV file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        menu_csv_path = os.path.join(current_dir, "..", "seed", "menu.csv")
        
        with open(menu_csv_path, "r") as f:
            menu_csv_content = f.read()
        
        import_menu(session, menu_csv_content)

import os
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.employee import Employee
from app.models.menu import MenuItem
from app.services.menu_import import import_menu
from app.core.security import hash_pin


SEED_EMPLOYEES = [
    {"number": 1, "code": "HOST1", "name": "Emma Carter", "role": "host"},
    {"number": 2, "code": "SRV1", "name": "Michael Brooks", "role": "server"},
    {"number": 3, "code": "KIT1", "name": "Carlos Diaz", "role": "kitchen"},
    {"number": 4, "code": "BAR1", "name": "Jessica Moore", "role": "bartender"},
    {"number": 5, "code": "ADM1", "name": "Linda Park", "role": "admin"},
    {"number": 6, "code": "SRV2", "name": "Daniel Hayes", "role": "server"},
    {"number": 7, "code": "SRV3", "name": "Sophia Turner", "role": "server"},
    {"number": 8, "code": "SRV4", "name": "James Walker", "role": "server"},
]


def seed_all(session: Session):
    """
    Idempotent seeding of employees and menu.
    
    Args:
        session: SQLAlchemy session
    """
    # Add any seed employee whose code is not in the database yet (safe to re-run)
    existing_codes = {code for (code,) in session.query(Employee.code).all()}
    for emp_data in SEED_EMPLOYEES:
        if emp_data["code"] not in existing_codes:
            session.add(Employee(
                number=emp_data["number"],
                code=emp_data["code"],
                name=emp_data["name"],
                role=emp_data["role"],
                positions=emp_data["role"],
                ssn_last=emp_data["code"][-1],
                pin_hash=hash_pin("1234"),
                location_id=1,
                active=True,
            ))

    # Seed menu if table is empty
    menu_item_count = session.query(MenuItem).count()
    if menu_item_count == 0:
        # Read and import the seed menu CSV file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        menu_csv_path = os.path.join(current_dir, "..", "seed", "menu.csv")
        
        with open(menu_csv_path, "r") as f:
            menu_csv_content = f.read()
        
        import_menu(session, menu_csv_content)

    session.commit()

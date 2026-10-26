import csv
from decimal import Decimal
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from app.models.menu import MenuItem, RecipeLine
from app.core.constants import CATEGORIES, CATEGORY_LABELS


def parse_menu_csv(text: str) -> List[Dict]:
    """
    Parse menu CSV text into a list of dictionaries.
    
    Args:
        text: CSV text with headers name,type,ingredient,qty,unit,sales
        
    Returns:
        List of dictionaries with keys: name, category, ingredient, qty, unit, price_cents
        
    Raises:
        ValueError: For invalid data including unknown type, missing/empty fields,
                   qty <= 0, or sales that differ between rows with the same name
    """
    # Parse CSV
    reader = csv.DictReader(text.strip().splitlines())
    rows = list(reader)
    
    if not rows:
        return []
    
    # Map type to category
    type_to_category = {
        "Bar": "bar",
        "Appetizers": "appetizers", 
        "Hot": "hot",
        "Cold": "cold"
    }
    
    # Store data to validate against later
    name_sales_map = {}
    
    result = []
    for i, row in enumerate(rows, 1):
        # Validate all fields exist and are not empty
        header_names = ["name", "type", "ingredient", "qty", "unit", "sales"]
        for header_name in header_names:
            if header_name not in row:
                raise ValueError(f"Missing header '{header_name}' on line {i}")
            if not row[header_name].strip():
                raise ValueError(f"Empty field '{header_name}' on line {i}")
        
        # Strip whitespace from all fields
        clean_row = {k: v.strip() for k, v in row.items()}
        
        # Convert quantity to float
        try:
            qty = float(clean_row["qty"])
            if qty <= 0:
                raise ValueError(f"Quantity must be greater than 0 on line {i}")
        except ValueError as e:
            if "could not convert string to float" in str(e):
                raise ValueError(f"Invalid quantity '{clean_row['qty']}' on line {i}")
            raise
        
        # Parse sales as Decimal (string representation)
        try:
            sales = Decimal(clean_row["sales"])
        except Exception:
            raise ValueError(f"Invalid sales amount '{clean_row['sales']}' on line {i}")
        
        # Map type to category
        row_type = clean_row["type"]
        if row_type not in type_to_category:
            raise ValueError(f"Unknown type '{row_type}' on line {i}")
            
        category = type_to_category[row_type]
        
        # Store sales for validation later
        name = clean_row["name"]
        if name not in name_sales_map:
            name_sales_map[name] = sales
        elif name_sales_map[name] != sales:
            raise ValueError(f"Sales amount differs between rows with same name '{name}' on line {i}")
        
        # Create result item
        item = {
            "name": name,
            "category": category,
            "ingredient": clean_row["ingredient"],
            "qty": qty,
            "unit": clean_row["unit"],
            "price_cents": int(sales * 100)
        }
        
        result.append(item)
    
    return result


def import_menu(session: Session, text: str) -> Tuple[int, int]:
    """
    Import menu from CSV text.
    
    Args:
        session: SQLAlchemy session
        text: CSV text to import
        
    Returns:
        Tuple of (item_count, recipe_line_count)
    """
    # Parse the CSV data
    items = parse_menu_csv(text)
    
    if not items:
        return 0, 0
    
    # Group by name and process each item
    items_by_name = {}
    for item in items:
        name = item["name"]
        if name not in items_by_name:
            items_by_name[name] = []
        items_by_name[name].append(item)
    
    item_count = 0
    recipe_line_count = 0
    
    for name, item_group in items_by_name.items():
        # Get the category and price from one of the items (they should all be the same)
        category = item_group[0]["category"]
        price_cents = item_group[0]["price_cents"]
        
        # Upsert MenuItem
        menu_item = session.query(MenuItem).filter(MenuItem.name == name).first()
        if not menu_item:
            menu_item = MenuItem(name=name, category=category, price_cents=price_cents)
            session.add(menu_item)
            session.flush()  # assign menu_item.id before recipe lines reference it
            item_count += 1
        else:
            # Update existing item with new category and price
            menu_item.category = category
            menu_item.price_cents = price_cents
            
        # Delete existing recipe lines
        session.query(RecipeLine).filter(RecipeLine.menu_item_id == menu_item.id).delete()
        
        # Add recipe lines
        for item in item_group:
            recipe_line = RecipeLine(
                menu_item_id=menu_item.id,
                ingredient=item["ingredient"],
                qty=item["qty"],
                unit=item["unit"]
            )
            session.add(recipe_line)
            recipe_line_count += 1
    
    session.commit()
    
    return item_count, recipe_line_count


def export_menu_csv(session: Session) -> str:
    """
    Export menu to CSV format.
    
    Args:
        session: SQLAlchemy session
        
    Returns:
        CSV text with header row and all recipe lines
    """
    # Get all menu items ordered by name
    menu_items = session.query(MenuItem).order_by(MenuItem.name).all()
    
    # Prepare data for export
    rows = []
    rows.append(["name", "type", "ingredient", "qty", "unit", "sales"])
    
    for item in menu_items:
        # Get category label
        category_label = CATEGORY_LABELS[item.category]
        
        # Add each recipe line
        for recipe_line in item.recipe_lines:
            sales = f"{item.price_cents / 100:.2f}"
            rows.append([
                item.name,
                category_label,
                recipe_line.ingredient,
                str(recipe_line.qty),
                recipe_line.unit,
                sales
            ])
    
    # Convert to CSV string
    output = []
    for row in rows:
        output.append(",".join(row))
    
    return "\n".join(output)

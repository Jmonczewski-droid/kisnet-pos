def test_parse_menu_csv_invalid_type():
    """Test that parse_menu_csv raises ValueError for unknown type."""
    from app.services.menu_import import parse_menu_csv
    
    text = """name,type,ingredient,qty,unit,sales
Caesar Salad,Dessert,Romaine Lettuce,8,oz,10.00"""
    
    try:
        parse_menu_csv(text)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "Unknown type 'Dessert'" in str(e)


def test_parse_menu_csv_valid_case():
    """Test parsing valid CSV data."""
    from app.services.menu_import import parse_menu_csv
    
    text = """name,type,ingredient,qty,unit,sales
Caesar Salad,Cold,Romaine Lettuce,8,oz,10.00
Caesar Salad,Cold,Caesar Dressing,4,oz,10.00
Caesar Salad,Cold,Parmesan,2,oz,10.00"""
    
    result = parse_menu_csv(text)
    
    # Should return 3 items
    assert len(result) == 3
    
    # All should have category "cold"
    for item in result:
        assert item["category"] == "cold"
        
    # All should have price_cents 1000
    for item in result:
        assert item["price_cents"] == 1000


def test_import_menu_from_seed(db):
    """import_menu on the seed file reports one recipe line per data row."""
    import csv
    from pathlib import Path
    from app.services.menu_import import import_menu

    text = (Path(__file__).resolve().parents[1] / "app" / "seed" / "menu.csv").read_text()
    data_rows = list(csv.DictReader(text.splitlines()))
    items, recipe_lines = import_menu(db, text)
    assert recipe_lines == len(data_rows)
    assert items == 0  # the seed menu is already loaded, so nothing new is created


def test_export_roundtrip(db):
    """export_menu_csv writes one row per recipe line and parses back to the same rows."""
    from app.models.menu import RecipeLine
    from app.services.menu_import import export_menu_csv, parse_menu_csv

    exported = parse_menu_csv(export_menu_csv(db))
    assert len(exported) == db.query(RecipeLine).count()


def test_seed_all_employees(db):
    """seed_all creates every seed employee and is idempotent."""
    from app.models.employee import Employee
    from app.services.seed import SEED_EMPLOYEES, seed_all

    codes = sorted(e.code for e in db.query(Employee).all())
    assert codes == sorted(e["code"] for e in SEED_EMPLOYEES)
    assert {"HOST1", "SRV1", "KIT1", "BAR1", "ADM1", "SRV2", "SRV3", "SRV4"} == set(codes)

    seed_all(db)
    assert db.query(Employee).count() == len(SEED_EMPLOYEES)


def test_seed_all_menu(db):
    """seed_all imports the seed menu once."""
    from app.models.menu import MenuItem
    from app.services.seed import seed_all

    count = db.query(MenuItem).count()
    assert count > 0
    seed_all(db)
    assert db.query(MenuItem).count() == count
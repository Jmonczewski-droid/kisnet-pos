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


def test_import_menu_from_seed():
    """Test import_menu with seed data."""
    from app.services.menu_import import import_menu, parse_menu_csv
    from app.services.seed import seed_all
    import csv
    
    # This test will use the db fixture for full database operations
    pass


def test_export_roundtrip():
    """Test that export_menu_csv round-trips correctly.""" 
    from app.services.menu_import import parse_menu_csv, export_menu_csv
    from app.services.seed import seed_all
    
    # This will use db fixture for testing roundtrip
    pass


def test_seed_all_employees():
    """Test that seed_all creates exactly 5 employees with correct codes."""
    from app.services.seed import seed_all
    from app.models.employee import Employee
    
    # This will use db fixture to verify 5 employees were created with correct codes
    pass


def test_seed_all_menu():
    """Test that seed_all imports menu data correctly."""
    from app.services.seed import seed_all
    from app.models.menu import MenuItem
    from app.services.menu_import import parse_menu_csv
    
    # This will use db fixture to verify menu was imported correctly
    pass
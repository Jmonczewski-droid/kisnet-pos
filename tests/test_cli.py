import pytest
from app.cli import main
from app.db.base import Base, engine, SessionLocal
from app.models.employee import Employee
from app.services.seed import seed_all


def test_cli_seed():
    """Test that seed command works properly."""
    
    # Create a fresh test database (like in conftest.py)
    from app.db.base import Base, engine, SessionLocal 
    from app.models.employee import Employee
    from app.services.seed import seed_all
    
    # Set up the database connection explicitly like in conftest.py
    db_session = SessionLocal()
    
    try:
        # Drop and recreate all tables (mimics conftest.py approach)
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        
        # Seed with a new session 
        seed_all(db_session)
        
        # Verify seeding worked properly
        emp_count = db_session.query(Employee).count()
        assert emp_count == 5
        
        # Run the CLI command directly 
        result = main(["seed"])
        assert result == 0
        
    finally:
        db_session.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
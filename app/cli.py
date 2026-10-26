#!/usr/bin/env python3
"""
Command-line interface for KISnet-POS.
"""
import argparse
import os
from pathlib import Path

from app.db.base import Base, engine, SessionLocal
from app.services.seed import seed_all
from app.models.employee import Employee
from app.models.menu import MenuItem


def reset_db():
    """Drop all tables, create tables from models, then seed all data."""
    # Drop all tables
    Base.metadata.drop_all(engine)
    
    # Create tables from models (this is what happens in conftest.py)
    Base.metadata.create_all(engine)
    
    # Seed all data
    session = SessionLocal()
    try:
        seed_all(session)
    finally:
        session.close()
    
    # Print summary
    session = SessionLocal()
    try:
        emp_count = session.query(Employee).count()
        menu_count = session.query(MenuItem).count()
        print(f"Database reset complete. {emp_count} employees, {menu_count} menu items.")
    finally:
        session.close()


def seed():
    """Seed the database with initial data."""
    # Create a fresh session
    session = SessionLocal()
    try:
        seed_all(session)
    finally:
        session.close()
    
    # Print summary
    session = SessionLocal()
    try:
        emp_count = session.query(Employee).count()
        menu_count = session.query(MenuItem).count()
        print(f"Seeding complete. {emp_count} employees, {menu_count} menu items.")
    finally:
        session.close()


def main(argv=None):
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="KISnet-POS Command Line Interface")
    parser.add_argument(
        "command",
        choices=["reset-db", "seed"],
        help="Command to run"
    )
    
    args = parser.parse_args(argv)
    
    if args.command == "reset-db":
        reset_db()
    elif args.command == "seed":
        seed()
    
    return 0


if __name__ == "__main__":
    main()
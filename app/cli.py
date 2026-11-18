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


def create_owner(name: str):
    """Add an owner card for a real business. Asks for a starter PIN; the owner picks their own at first sign-in."""
    import getpass
    from types import SimpleNamespace
    from app.services.admin import add_employee

    pin = getpass.getpass("Starter PIN for the owner (4 or more characters): ")
    if len(pin) < 4:
        print("The PIN must be at least 4 characters. Nothing was created.")
        return 1
    session = SessionLocal()
    try:
        data = SimpleNamespace(name=name, positions=[], access="owner", address=None, dob=None, hire_date=None, pin=pin)
        employee = add_employee(session, data)
        print(f"Owner created: {employee.name}, employee code {employee.code}.")
        print("Clock in with that code and the starter PIN; you will be asked to choose your own PIN.")
    finally:
        session.close()
    return 0


def reset_two_step(code: str):
    """Turn off two-step sign-in for one employee (for an owner who lost their phone). Needs access to this computer."""
    from app.services.auth import clear_totp

    session = SessionLocal()
    try:
        employee = session.query(Employee).filter_by(code=code).first()
        if not employee:
            print(f"No employee with code {code}.")
            return 1
        clear_totp(employee)
        employee.failed_attempts = 0
        employee.locked_until = None
        session.commit()
        print(f"Two-step sign-in is off for {employee.code} {employee.name}. Set it up again under Sign-in Security.")
    finally:
        session.close()
    return 0


def main(argv=None):
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="KISnet-POS Command Line Interface")
    parser.add_argument(
        "command",
        choices=["reset-db", "seed", "create-owner", "reset-two-step"],
        help="Command to run"
    )
    parser.add_argument("value", nargs="?", help="create-owner: the owner's name. reset-two-step: the employee code.")
    
    args = parser.parse_args(argv)
    
    if args.command == "reset-db":
        reset_db()
    elif args.command == "seed":
        seed()
    elif args.command in ("create-owner", "reset-two-step"):
        if not args.value:
            parser.error(f"{args.command} needs a value: " + ("the owner's name" if args.command == "create-owner" else "the employee code"))
        return create_owner(args.value) if args.command == "create-owner" else reset_two_step(args.value)
    
    return 0


if __name__ == "__main__":
    main()
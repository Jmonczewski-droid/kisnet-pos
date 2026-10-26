---
allowed: app/models/__init__.py, app/models/party.py, app/models/order.py, tests/test_models_orders.py
verify: venv/bin/python -m pytest -q tests/test_models_orders.py
---
Read .qwen/CONVENTIONS.md first and follow it exactly.
Create app/models/party.py (Party) and app/models/order.py (Order, OrderItem, OrderItemIngredient) exactly as
the conventions describe, using Base from app.db.base. Update app/models/__init__.py to also import Party,
Order, OrderItem, OrderItemIngredient (keep the existing imports). Do not edit app/db/base.py.
tests/test_models_orders.py: fresh in-memory sqlite engine, create_all, insert an Employee, a Party with a
server, an Order with two OrderItems (one with an OrderItemIngredient), query back, assert values, and assert
party.orders and order.items ordering by id. Do not use conftest.py.
Do not create any other files.

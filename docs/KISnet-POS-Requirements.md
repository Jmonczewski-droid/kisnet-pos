# KISnet-POS — Requirements (v0.2)

Lightweight, app-based POS for small restaurants and franchises.
**Source of truth: the KISnet-POS workflow document.** Section A is taken directly from it. Section B lists optional suggestions that are not in the source document; nothing in Section B is required unless you choose to adopt it.

Stations (per the workflow document): **Admin, Host, Server, Bar, Kitchen.**

---

# Section A — Core requirements (from the workflow document)

## A1. Workflow

- **FLOW-01** Employee logs in.
- **FLOW-02** Employee loads to their job-specific page.
- **FLOW-03** Host or Bar creates a party.
- **FLOW-04** Server/Bartender selects a table and can place and edit the order.
- **FLOW-05** Kitchen receives the order.

## A2. Admin

- **ADM-01** Admin loads to the **Command Center** screen after login.
- **ADM-02** Admin has all privileges.
- **ADM-03** A drop-down menu on the left switches between screens (Command Center, Host, Server, Bar, Kitchen, and reports).
- **ADM-04** Command Center shows all employees currently on the clock.

## A3. Host screen

- **HOST-01** 4×4 grid of squares, rows A–D, columns 1–4 (A1–D4).
- **HOST-02** **Create Party** = Table + Assigned Server + Party Name + Party Size.
- **HOST-03** Creating a party starts the order time for that table.

## A4. Server screen

- **SRV-01** Server has a drop-down of the tables assigned to them on the Host screen.
- **SRV-02** Server can place and edit an order for a selected table.
- **SRV-03** **Create Order** exports to Bar and Kitchen (drink items to Bar, food items to Kitchen).

## A5. Bar screen

- **BAR-01** 10 circles labeled Z1–Z10.
- **BAR-02** Bartender can create a party on a Z seat.
- **BAR-03** Bartender can place and edit orders.
- **BAR-04** **Create Order** exports to Bar and Kitchen.

## A6. Kitchen screen

- **KIT-01** Primary screen has 3 tracks: **Appetizers**, **Hot**, **Cold**.
- **KIT-02** Each order shows a running time and the table number.
- **KIT-03** Items route to the track matching their type.

## A7. Database — menu and recipes

- **DB-01** Food items are stored in the backend with their recipe, in CSV form.
- **DB-02** Each item is assigned one category: **Bar** (drinks), **Appetizers**, **Hot**, or **Cold**.
- **DB-03** Each item record has: Name, Type, Items (ingredients with quantities), Sales (price).

Example from the workflow document:

```
Name  - Caesar Salad
Type  - Cold
Item  - 8 oz Romaine Lettuce
        4 oz Caesar Dressing
        2 oz Parm
Sales - $10
```

Suggested CSV layout, one row per ingredient line:

```csv
name,type,ingredient,qty,unit,sales
Caesar Salad,Cold,Romaine Lettuce,8,oz,10.00
Caesar Salad,Cold,Caesar Dressing,4,oz,10.00
Caesar Salad,Cold,Parmesan,2,oz,10.00
```

- **DB-04** The MVP is populated with real, generic recipes across all four categories.

## A8. Database — reports

- **RPT-01** Completed orders are imported to create reports.
- **RPT-02** **Daily Sales** report.
- **RPT-03** **Food Usage** report.
- **RPT-04** Store usage of all items by name, type, item (ingredient), and sales.
- **RPT-05** Food Usage adds up all items sold, by item. Ingredient usage = quantity sold × recipe quantity, summed per ingredient.

## A9. Created employees

- **EMP-01** Fake employees with generic male or female names, coded by role:

| Code | Name | Role |
|---|---|---|
| HOST1 | Emma Carter | Host |
| SRV1 | Michael Brooks | Server |
| KIT1 | Carlos Diaz | Kitchen |
| BAR1 | Jessica Moore | Bartender |
| ADM1 | Linda Park | Admin (needed to log in to Command Center) |

Add HOST2, SRV2, and so on as needed for testing multiple servers.

## A10. Open points the workflow document implies but doesn't define

These need a decision from you so the build matches your intent:

1. **"On the clock" (ADM-04):** how does an employee clock in — automatically at login, or a separate clock-in action? And how do they clock out?
2. **"Completed order" (RPT-01):** who marks an order complete, and from which screen (Server/Bar)?
3. **Kitchen finish action:** how does the kitchen clear an order off a track (for example, tap to bump)?
4. **Clearing a table:** what returns a Host table to available after the party leaves?
5. **Bar tickets:** where do drink orders appear on the Bar screen alongside the Z1–Z10 circles?

## A11. MVP acceptance test

1. HOST1 logs in, creates party "Smith", size 4, at B2, server SRV1. Order time starts.
2. SRV1 logs in, selects B2 from their drop-down, orders 2 Caesar Salads, 1 Burger, 2 beers, and creates the order.
3. Kitchen shows the Caesar Salads on the Cold track and the Burger on the Hot track, each with table B2 and a running time. Bar receives the beers.
4. BAR1 creates a party at Z3 and orders a drink and an appetizer. The appetizer appears on the Appetizers track as Z3.
5. The orders are completed.
6. ADM1 sees all four employees on the clock in Command Center, then runs Daily Sales (both orders) and Food Usage (Romaine 16 oz, Caesar Dressing 8 oz, Parmesan 4 oz, plus the other items' ingredients).

---

# Section B — Optional suggestions (not in the workflow document)

Adopt, change, or drop any of these. They are ordered roughly by how much trouble they prevent.

- **SUG-01** Order and kitchen timers use timestamps saved on the server, so refreshing a screen never resets them.
- **SUG-02** Kitchen screen updates live, without reloading the page.
- **SUG-03** Each item sold saves a copy of its name, price, and recipe at the time of sale, so editing a recipe later doesn't change past reports.
- **SUG-04** PostgreSQL holds the live menu; CSV is used to import and export it.
- **SUG-05** Money stored as whole cents, not decimals that can round wrong.
- **SUG-06** PIN-based login, stored hashed, with role checks enforced by the backend.
- **SUG-07** Edits after an order is sent show clearly in the kitchen.
- **SUG-08** A `location_id` on records, to support franchises later.
- **SUG-09** A single reset command that reloads the seed employees and menu.
- **SUG-10** Nightly database backup.
- **SUG-11** Later features: payment/tax/tips, voids with manager approval, waitlist, reports exported to CSV.

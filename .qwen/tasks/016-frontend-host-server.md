---
allowed: app/static/app.js, app/static/styles.css
max_attempts: 6
verify: node --check app/static/app.js && grep -q 'renderHost' app/static/app.js && grep -q 'renderServer' app/static/app.js
---
Read .qwen/CONVENTIONS.md first and follow it exactly. app/static/app.js and styles.css exist from task 015; extend them (keep existing code; only add/replace the Host and Server screens and needed CSS).
- renderHost(root): 4x4 grid A-D rows, columns 1-4 from GET /api/v1/seats; occupied seats show party name and elapsed time (fmtElapsed of opened_at); click an empty table seat to open a "Create Party" form: party name, party size, and an assigned server dropdown populated from GET /api/v1/employees?role=server (value = employee id). Submit POST /api/v1/parties with seat, party_name, party_size, server_id. Clicking an occupied seat shows the party detail with a "Close table" button (POST /api/v1/parties/{id}/close) that shows the error text on 409.
- renderServer(root): dropdown of open parties from GET /api/v1/parties?open=true. Selecting one shows party detail (GET /api/v1/parties/{id}) with open order items (name, qty, notes, changed/voided/bumped badges), a menu list from GET /api/v1/menu grouped by category with qty steppers and notes, a "Create Order" button (POST /api/v1/parties/{id}/items with the selected lines), per-line PATCH qty and DELETE to void, and a "Complete order" button (POST /api/v1/parties/{id}/complete). Refresh the view after each action.
Keep functions small. Do not create other files.

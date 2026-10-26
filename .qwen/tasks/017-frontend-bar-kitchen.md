---
allowed: app/static/app.js, app/static/styles.css
max_attempts: 6
verify: node --check app/static/app.js && grep -q 'renderBar' app/static/app.js && grep -q 'renderKitchen' app/static/app.js
---
Read .qwen/CONVENTIONS.md first and follow it exactly. app/static/app.js already has Host and Server screens from task 016; keep them and add the Bar and Kitchen screens.
- renderBar(root): 10 circles Z1-Z10 from GET /api/v1/seats (bar seats only). Empty circle click -> create-party form (party name, size; POST /api/v1/parties with seat). Occupied circle -> party panel reusing the Server order UI (menu grouped by category, Create Order, qty PATCH, void DELETE, Complete order) and a Close button (POST /api/v1/parties/{id}/close). Also a "Bar tickets" list from GET /api/v1/tickets?track=bar with a Bump button (POST /api/v1/tickets/{order_id}/bar/bump).
- renderKitchen(root): three columns Appetizers, Hot, Cold from GET /api/v1/tickets?track=<t>, refreshed every 2 seconds with setInterval (clear the interval when leaving the screen: store on window.KIS and clear in go()). Each ticket card shows seat, party name, running time (fmtElapsed of opened_at), item lines with qty, notes, NEW/CHANGED/VOID badges, and a Bump button (POST /api/v1/tickets/{order_id}/{track}/bump).
Register renderBar and renderKitchen in SCREENS. Keep functions small. Do not create other files.

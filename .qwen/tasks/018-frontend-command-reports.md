---
allowed: app/static/app.js, app/static/styles.css
max_attempts: 6
verify: node --check app/static/app.js && grep -q 'renderCommand' app/static/app.js && grep -q 'renderReports' app/static/app.js
---
Read .qwen/CONVENTIONS.md first and follow it exactly. app/static/app.js has Host, Server, Bar, Kitchen screens from tasks 016-017; keep them and add the admin screens.
- renderCommand(root): Command Center table of employees on the clock from GET /api/v1/admin/on-clock (code, name, role, clocked-in time via fmtDate and elapsed); a "Clock out" button per row (POST /api/v1/admin/clock-out/{employee_id}); refreshed every 10 seconds, interval cleared when leaving the screen.
- renderReports(root): date inputs start and end (default today, YYYY-MM-DD), Daily Sales button -> GET /api/v1/reports/daily-sales?start=&end= rendered as a table (name, category label, qty, sales in dollars from cents) with a totals row; Food Usage button -> GET /api/v1/reports/food-usage rendered as a table (ingredient, unit, qty to 2 decimals). Menu admin: a "Download menu CSV" button that fetches /api/v1/menu/export with the token and downloads a Blob; and a file input that POSTs its text to /api/v1/menu/import with content-type text/csv, showing the counts.
- Register renderCommand and renderReports in SCREENS. Sidebar for admin lists all six screens.
Keep functions small. Do not create other files.

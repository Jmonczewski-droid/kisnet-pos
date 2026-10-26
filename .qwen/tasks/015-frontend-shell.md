---
allowed: app/static/index.html, app/static/styles.css, app/static/app.js
max_attempts: 6
verify: node --check app/static/app.js && grep -q 'id="app"' app/static/index.html && grep -q 'styles.css' app/static/index.html
---
Read .qwen/CONVENTIONS.md first and follow it exactly. Vanilla JS, no build step, no external CDN.
Create the app shell:
- index.html: loads /static/styles.css and /static/app.js (defer); contains <div id="app"></div>.
- app.js: api(path, opts) helper that prefixes /api/v1, sends Bearer token from localStorage key "kisnet.token", parses JSON, throws Error(detail) on non-2xx. Hash-based router: #/login (Home login form: employee code + PIN fields, "Clock in" button; on success store token and employee, route by role: admin -> #/command, host -> #/host, server -> #/server, bartender -> #/bar, kitchen -> #/kitchen). Station layout: left sidebar nav (admin sees all screens: Command Center, Host, Server, Bar, Kitchen, Reports; others see only their station), top bar with employee name, role and a "Clock out" button (POST /auth/clock-out then back to login). Each screen is a function renderX(root) registered in a SCREENS map; this task renders placeholder "Coming soon" text for each. Expose window.KIS = { api, state, go, SCREENS } for later tasks.
- fmtDate(iso): appends "Z" if the string has no timezone, returns a locale time string. fmtElapsed(iso): returns mm:ss since that time.
- styles.css: readable layout: sidebar + main, cards, tables, grid buttons, large touch-friendly buttons. Keep under ~200 lines.
Create only these three files.

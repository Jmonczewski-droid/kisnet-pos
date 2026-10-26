// API helper function
function api(path, opts = {}) {
    const url = path.startsWith('/api/v1') ? path : '/api/v1' + path;
    const defaultOpts = {
        headers: {
            'Content-Type': 'application/json',
        }
    };
    
    // Add Bearer token if available
    const token = localStorage.getItem('kisnet.token');
    if (token) {
        defaultOpts.headers['Authorization'] = `Bearer ${token}`;
    }
    
    const options = { ...defaultOpts, ...opts };
    
    return fetch(url, options)
        .then(response => {
            if (!response.ok) {
                if (response.status === 401 && token && !path.includes('/auth/clock-in')) {
                    expireSession();
                }
                return response.json().then(err => {
                    throw new Error(err.detail || `HTTP error! status: ${response.status}`);
                });
            }
            // 204 No Content (e.g. voiding an item) has no body to parse
            return response.status === 204 ? null : response.json();
        });
}

// State management
const state = {
    employee: null,
    token: null
};

// Hash-based router
function go(path) {
    window.location.hash = path;
}

// Go to a path; if the hash is already there, the browser fires no hashchange, so render directly
function goTo(path) {
    if (window.location.hash.slice(1) === path) {
        updateScreen();
    } else {
        go(path);
    }
}

// Home screen for each role (admin can open any screen)
function stationFor(role) {
    return { admin: '/command', host: '/host', server: '/server', bartender: '/bar', kitchen: '/kitchen' }[role];
}

function canVisit(role, path) {
    return role === 'admin' ? path in SCREENS : (path === stationFor(role) || path === '/timecard');
}

// Idle sign-out: after this long with no input, return to login and resume the same page after signing in
const IDLE_LIMIT_MS = 5 * 60 * 1000;
let lastActivity = Date.now();

function expireSession() {
    const token = localStorage.getItem('kisnet.token');
    if (token) {
        fetch('/api/v1/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    }
    const current = window.location.hash;
    if (current && current !== '#/login') {
        localStorage.setItem('kisnet.returnTo', current);
    }
    localStorage.removeItem('kisnet.token');
    state.employee = null;
    state.token = null;
    stopScreenTimers();
    renderMenu();
    go('#/login');
}

// Format date helper
// Server timestamps are naive UTC; read them as UTC
function parseServerTime(iso) {
    if (!iso.includes('Z') && !iso.match(/\+.*|-[0-9]{4}$/)) {
        iso += 'Z';
    }
    return new Date(iso);
}

function fmtDate(iso) {
    if (!iso) return '';
    return parseServerTime(iso).toLocaleString();
}

// Format elapsed time helper
function fmtElapsed(iso) {
    if (!iso) return '';
    const date = parseServerTime(iso);
    const now = new Date();
    const diffInSeconds = Math.max(0, Math.floor((now - date) / 1000));
    
    const minutes = Math.floor(diffInSeconds / 60);
    const seconds = diffInSeconds % 60;
    
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

// Show create party form for empty seat
function showCreatePartyForm(root, seat) {
    api('/api/v1/employees?role=server')
        .then(servers => {
            root.innerHTML = `
                <div class="card">
                    <h2>Create New Party</h2>
                    <div class="form-group">
                        <label for="party-name">Party Name</label>
                        <input type="text" id="party-name" placeholder="Enter party name">
                    </div>
                    <div class="form-group">
                        <label for="party-size">Party Size</label>
                        <input type="number" id="party-size" min="1" value="2">
                    </div>
                    <div class="form-group">
                        <label for="server-select">Assigned Server</label>
                        <select id="server-select">
                            ${servers.map(server => `<option value="${server.id}">${server.name}</option>`).join('')}
                        </select>
                    </div>
                    <button id="create-party-btn" class="btn-large">Create Party</button>
                    <button id="cancel-create-btn" class="btn-large">Cancel</button>
                </div>
            `;
            
            document.getElementById('create-party-btn').addEventListener('click', function() {
                const partyName = document.getElementById('party-name').value;
                const partySize = parseInt(document.getElementById('party-size').value);
                const serverId = parseInt(document.getElementById('server-select').value);
                
                if (!partyName || !partySize || partySize < 1) {
                    alert('Please enter a valid party name and size');
                    return;
                }
                
                api('/api/v1/parties', {
                    method: 'POST',
                    body: JSON.stringify({
                        seat: seat,
                        party_name: partyName,
                        party_size: partySize,
                        server_id: serverId
                    })
                })
                .then(() => {
                    // Refresh the host screen after successful creation
                    renderHost(root);
                })
                .catch(error => {
                    alert('Error creating party: ' + error.message);
                    console.error('Error creating party:', error);
                });
            });
            
            document.getElementById('cancel-create-btn').addEventListener('click', function() {
                // Refresh the host screen to show updated state
                renderHost(root);
            });
        })
        .catch(error => {
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${error.message}</p></div>`;
            console.error('Error loading servers:', error);
        });
}

// Render party details (for both host and server screens)
// Small pop-up beside a menu item asking to add it to the party's order
function showAddItemPopover(button, item, party, root) {
    closeItemPopover();
    const popover = document.createElement('div');
    popover.id = 'item-popover';
    popover.className = 'item-popover';
    popover.innerHTML = `
        <p><strong>Add ${escapeHtml(item.name)}?</strong></p>
        <div class="form-group">
            <label for="pop-qty">Qty</label>
            <input type="number" id="pop-qty" min="1" value="1">
        </div>
        <div class="form-group">
            <input type="text" id="pop-notes" placeholder="Notes (optional)">
        </div>
        <div class="item-popover-actions">
            <button id="pop-add-btn" class="btn-large">Add</button>
            <button id="pop-cancel-btn" class="btn-large">Cancel</button>
        </div>`;
    document.body.appendChild(popover);

    // Place it to the right of the clicked item, or to the left if there is no room
    const rect = button.getBoundingClientRect();
    const width = popover.offsetWidth || 220;
    const left = rect.right + 8 + width <= window.innerWidth ? rect.right + 8 : rect.left - width - 8;
    popover.style.top = `${Math.max(8, rect.top)}px`;
    popover.style.left = `${Math.max(8, left)}px`;

    popover.querySelector('#pop-cancel-btn').addEventListener('click', closeItemPopover);
    popover.querySelector('#pop-add-btn').addEventListener('click', () => {
        const qty = parseInt(popover.querySelector('#pop-qty').value, 10);
        const notes = popover.querySelector('#pop-notes').value.trim() || null;
        if (!(qty >= 1)) {
            alert('Quantity must be at least 1');
            return;
        }
        api(`/api/v1/parties/${party.id}/items`, {
            method: 'POST',
            body: JSON.stringify({ items: [{ menu_item_id: parseInt(item.id, 10), qty, notes }] })
        })
        .then(() => {
            closeItemPopover();
            // Reload this party so the selection stays and the order shows the new line
            return api(`/api/v1/parties/${party.id}`).then(updated => renderPartyDetails(root, updated, 'server'));
        })
        .catch(error => alert('Could not add item: ' + error.message));
    });

    // Clicking anywhere outside the pop-up closes it
    const outside = (event) => {
        if (!popover.contains(event.target) && event.target !== button) {
            closeItemPopover();
        }
    };
    popover._outside = outside;
    setTimeout(() => document.addEventListener('pointerdown', outside, true), 0);
    popover.querySelector('#pop-qty').focus();
}

function closeItemPopover() {
    const popover = document.getElementById('item-popover');
    if (!popover) return;
    document.removeEventListener('pointerdown', popover._outside, true);
    popover.remove();
}

// ---- Server ticket panel: the current ticket, live, with edits on a selected line ----

const TICKET_REFRESH_MS = 3000;

function showTicketPanel(party) {
    window.KIS.ticket = window.KIS.ticket || { partyId: null, selectedId: null, party: null, interval: null };
    const ticket = window.KIS.ticket;
    if (ticket.partyId !== party.id) {
        ticket.selectedId = null;
    }
    ticket.partyId = party.id;
    ticket.party = party;

    if (!document.getElementById('ticket-panel')) {
        const panel = document.createElement('aside');
        panel.id = 'ticket-panel';
        panel.className = 'ticket-panel';
        panel.innerHTML = `
            <h3 id="ticket-title"></h3>
            <p id="ticket-status" class="status-note"></p>
            <div id="ticket-list"></div>
            <div id="ticket-editor" class="ticket-editor"></div>`;
        document.body.appendChild(panel);
        document.body.classList.add('ticket-open');
        document.getElementById('ticket-list').addEventListener('click', (event) => {
            const row = event.target.closest('.ticket-row');
            if (!row) return;
            ticket.selectedId = parseInt(row.dataset.itemId, 10);
            drawTicketList();
            drawTicketEditor();
        });
    }

    drawTicketList();
    drawTicketEditor();
    if (!ticket.interval) {
        ticket.interval = setInterval(refreshTicketPanel, TICKET_REFRESH_MS);
    }
}

function stopTicketPanel() {
    const ticket = window.KIS && window.KIS.ticket;
    if (ticket && ticket.interval) {
        clearInterval(ticket.interval);
        ticket.interval = null;
    }
    const panel = document.getElementById('ticket-panel');
    if (panel) panel.remove();
    document.body.classList.remove('ticket-open');
}

// Reload the party so the panel shows the latest ticket (keeps the selected line and any typing)
function refreshTicketPanel() {
    const ticket = window.KIS.ticket;
    if (!ticket || !ticket.partyId || !document.getElementById('ticket-panel')) return;
    api(`/api/v1/parties/${ticket.partyId}`)
        .then(party => {
            ticket.party = party;
            drawTicketList();
            if (ticket.selectedId && !currentTicketItem()) {
                ticket.selectedId = null;
                drawTicketEditor();
            }
            setTicketStatus('');
        })
        .catch(error => setTicketStatus(`Could not refresh (${error.message}). Retrying...`));
}

function setTicketStatus(text) {
    const status = document.getElementById('ticket-status');
    if (status) status.textContent = text;
}

function ticketItems() {
    const party = window.KIS.ticket && window.KIS.ticket.party;
    return party && party.open_order ? party.open_order.items : [];
}

function currentTicketItem() {
    return ticketItems().find(item => item.id === window.KIS.ticket.selectedId) || null;
}

function drawTicketList() {
    const ticket = window.KIS.ticket;
    const list = document.getElementById('ticket-list');
    const title = document.getElementById('ticket-title');
    if (!list || !ticket || !ticket.party) return;

    title.textContent = `Ticket: ${ticket.party.seat} - ${ticket.party.party_name}`;
    const items = ticketItems();
    if (items.length === 0) {
        list.innerHTML = '<p>No items on this ticket yet.</p>';
        return;
    }
    list.innerHTML = items.map(item => {
        const badges = [
            item.voided ? 'VOID' : '',
            !item.voided && item.bumped ? 'SENT' : '',
            !item.voided && item.changed ? 'CHANGED' : ''
        ].filter(Boolean);
        return `
            <div class="ticket-row ${item.id === ticket.selectedId ? 'selected' : ''} ${item.voided ? 'voided' : ''}" data-item-id="${item.id}">
                <strong>${escapeHtml(item.name)}</strong> x${item.qty}
                <span class="ticket-price">$${(item.line_total_cents / 100).toFixed(2)}</span>
                ${badges.map(b => `<span class="ticket-badge">${b}</span>`).join('')}
                ${item.notes ? `<div class="ticket-notes">${escapeHtml(item.notes)}</div>` : ''}
            </div>`;
    }).join('') + `<p class="ticket-total">Total: $${(ticketTotalCents() / 100).toFixed(2)}</p>`;
}

function ticketTotalCents() {
    return ticketItems().reduce((sum, item) => sum + item.line_total_cents, 0);
}

// Editor for the selected line. Only rebuilt on selection or after a save, so typing survives refreshes.
function drawTicketEditor() {
    const editor = document.getElementById('ticket-editor');
    if (!editor) return;
    const item = currentTicketItem();
    if (!item) {
        editor.innerHTML = '<p class="ticket-hint">Select an item to change it.</p>';
        return;
    }
    const locked = item.voided || item.bumped;
    editor.innerHTML = `
        <h4>${escapeHtml(item.name)}</h4>
        ${locked ? `<p class="status-note">${item.voided ? 'Voided' : 'Already sent to the kitchen or bar; it cannot be changed.'}</p>` : ''}
        <div class="qty-row">
            <button id="tk-dec" ${locked ? 'disabled' : ''}>-</button>
            <input id="tk-qty" type="number" min="1" value="${item.qty}" ${locked ? 'disabled' : ''}>
            <button id="tk-inc" ${locked ? 'disabled' : ''}>+</button>
        </div>
        <input id="tk-notes" type="text" placeholder="Notes" value="${escapeHtml(item.notes || '')}" ${locked ? 'disabled' : ''}>
        <div class="ticket-editor-actions">
            <button id="tk-save" class="btn-large" ${locked ? 'disabled' : ''}>Save</button>
            <button id="tk-void" class="btn-large" ${locked ? 'disabled' : ''}>Void item</button>
        </div>`;
    if (locked) return;

    const qtyInput = document.getElementById('tk-qty');
    document.getElementById('tk-dec').addEventListener('click', () => {
        qtyInput.value = Math.max(1, (parseInt(qtyInput.value, 10) || 1) - 1);
    });
    document.getElementById('tk-inc').addEventListener('click', () => {
        qtyInput.value = (parseInt(qtyInput.value, 10) || 0) + 1;
    });
    document.getElementById('tk-save').addEventListener('click', () => {
        const qty = parseInt(qtyInput.value, 10);
        if (!(qty >= 1)) {
            alert('Quantity must be at least 1');
            return;
        }
        api(`/api/v1/order-items/${item.id}`, {
            method: 'PATCH',
            body: JSON.stringify({ qty, notes: document.getElementById('tk-notes').value.trim() })
        })
        .then(() => refreshTicketPanel())
        .catch(error => alert('Could not save change: ' + error.message));
    });
    document.getElementById('tk-void').addEventListener('click', () => {
        if (!confirm(`Void ${item.name}?`)) return;
        api(`/api/v1/order-items/${item.id}`, { method: 'DELETE' })
            .then(() => refreshTicketPanel())
            .catch(error => alert('Could not void item: ' + error.message));
    });
}

function renderPartyDetails(root, party, role) {
    const isHostScreen = role === 'host';
    const isServerScreen = role === 'server';
    
    // First get the menu items
    api('/api/v1/menu')
        .then(menuItems => {
            const menuCategories = {};
            menuItems.forEach(item => {
                if (!menuCategories[item.category]) {
                    menuCategories[item.category] = [];
                }
                menuCategories[item.category].push(item);
            });
            
            const partyDetails = `
                <div class="card" id="party-details-card">
                    <h2>Party Details</h2>
                    <p><strong>Seat:</strong> ${party.seat}</p>
                    <p><strong>Party Name:</strong> ${party.party_name}</p>
                    <p><strong>Party Size:</strong> ${party.party_size}</p>
                    <p><strong>Server:</strong> ${party.server_name || 'None'}</p>
                    <p><strong>Started:</strong> ${fmtDate(party.opened_at)}</p>
                    <p><strong>Elapsed:</strong> ${fmtElapsed(party.opened_at)} minutes</p>
                    
                    ${isHostScreen && party.closed_at ? 
                        `<p><strong>Closed:</strong> ${fmtDate(party.closed_at)}</p>` : ''}
                    
                    ${isHostScreen && !party.closed_at ? 
                        `<button class="btn-large" id="close-table-btn">Close Table</button>` : ''}
                        
                    ${party.open_order && !isServerScreen ? `
                        <h3>Current Order</h3>
                        <div id="order-items">
                            ${party.open_order.items.map(item => {
                                const statusClass = item.voided ? 'voided' : item.changed ? 'changed' : '';
                                const statusText = item.voided ? '(VOIDED)' : item.changed ? '(CHANGED)' : '';
                                return `
                                    <div class="order-item ${statusClass}">
                                        <p><strong>${item.name}</strong> - Qty: ${item.qty} 
                                            ${item.notes ? ` | Notes: ${item.notes}` : ''}
                                            ${statusText}
                                        </p>
                                        <p>Price: $${(item.unit_price_cents / 100).toFixed(2)}</p>
                                    </div>
                                `;
                            }).join('')}
                        </div>
                    ` : ''}
                    
                    ${isServerScreen && party.open_order ? `
                        <button class="btn-large" id="complete-order-btn">Complete Order</button>
                    ` : ''}
                    
                    ${isServerScreen && !party.closed_at ? `
                        <h3>Menu Items</h3>
                        <div id="menu-category-list">
                            ${Object.entries(menuCategories).map(([category, items]) => `
                                <h4>${category.charAt(0).toUpperCase() + category.slice(1)}</h4>
                                <div class="grid-buttons">
                                    ${items.map(item => `
                                        <button 
                                            class="menu-item-btn"
                                            data-item-id="${item.id}"
                                            data-category="${item.category}"
                                            data-name="${item.name}"
                                            data-price="${item.price_cents}"
                                        >
                                            ${item.name}<br>
                                            $${(item.price_cents / 100).toFixed(2)}
                                        </button>
                                    `).join('')}
                                </div>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            `;
            
            root.innerHTML = partyDetails;
            if (isServerScreen) {
                showTicketPanel(party);
            }
            
            // Add event listeners for host screen buttons
            if (isHostScreen && !party.closed_at) {
                document.getElementById('close-table-btn').addEventListener('click', function() {
                    api(`/api/v1/parties/${party.id}/close`, { method: 'POST' })
                        .then(() => {
                            // Refresh the host screen after successful close
                            renderHost(root);
                        })
                        .catch(error => {
                            if (error.message.includes('409')) {
                                alert('Cannot close table: an open order exists on this table.');
                            } else {
                                alert('Error closing table: ' + error.message);
                            }
                            console.error('Error closing table:', error);
                        });
                });
            }
            
            // Add event listeners for server screen buttons
            if (isServerScreen && party.open_order) {
                document.getElementById('complete-order-btn').addEventListener('click', function() {
                    api(`/api/v1/parties/${party.id}/complete`, { method: 'POST' })
                        .then(() => {
                            // Refresh the server screen after successful completion
                            renderServer(root);
                        })
                        .catch(error => {
                            alert('Error completing order: ' + error.message);
                            console.error('Error completing order:', error);
                        });
                });
            }
            
            // Clicking a menu item asks, in a small pop-up beside it, whether to add it
            if (isServerScreen && !party.closed_at) {
                document.querySelectorAll('.menu-item-btn').forEach(button => {
                    button.addEventListener('click', function() {
                        showAddItemPopover(this, { id: this.dataset.itemId, name: this.dataset.name }, party, root);
                    });
                });
            }
        })
        .catch(error => {
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${error.message}</p></div>`;
            console.error('Error loading menu items:', error);
        });
}
function renderLogin(root) {
    root.innerHTML = `
        <div class="login-container">
            <div class="card">
                <h2>KISnet POS: Clock In</h2>
                <div class="form-group">
                    <label for="employee-code">Employee Code</label>
                    <input type="text" id="employee-code" placeholder="e.g. HOST1">
                </div>
                <div class="form-group">
                    <label for="pin">PIN</label>
                    <input type="password" id="pin" placeholder="Enter your PIN">
                </div>
                <button id="clock-in-btn" class="btn-large">Clock In</button>
            </div>
        </div>
    `;
    
    document.getElementById('clock-in-btn').addEventListener('click', handleLogin);
}

function handleLogin() {
    const code = document.getElementById('employee-code').value;
    const pin = document.getElementById('pin').value;

    if (!code || !pin) {
        alert('Please enter both employee code and PIN');
        return;
    }

    api('/auth/preview', { method: 'POST', body: JSON.stringify({ code, pin }) })
        .then(preview => {
            // Already on the clock: sign straight in. Otherwise confirm the clock in first.
            if (preview.on_clock) {
                return completeClockIn(code, pin);
            }
            confirmClockIn(preview, code, pin);
        })
        .catch(error => alert('Login failed: ' + error.message));
}

function roleLabel(role) {
    return role.charAt(0).toUpperCase() + role.slice(1);
}

// Pop-up asking the person to confirm their clock in
function confirmClockIn(preview, code, pin) {
    const employee = preview.employee;
    const body = openModal('Confirm clock in', `
        <p><strong>Name:</strong> ${escapeHtml(employee.name)}</p>
        <p><strong>Position:</strong> ${escapeHtml(roleLabel(employee.role))}</p>
        <p><strong>Time:</strong> ${fmtDate(preview.now)}</p>
        <p>Clock in now?</p>
        <button id="confirm-clock-in-btn" class="btn-large">Confirm clock in</button>
        <button id="cancel-clock-in-btn" class="btn-large">Cancel</button>
    `);

    body.querySelector('#cancel-clock-in-btn').addEventListener('click', closeModal);
    body.querySelector('#confirm-clock-in-btn').addEventListener('click', () => {
        closeModal();
        completeClockIn(code, pin).catch(error => alert('Login failed: ' + error.message));
    });
}

// Clock in (or sign back in) and open the station, or the page the user was on
function completeClockIn(code, pin) {
    return api('/auth/clock-in', { method: 'POST', body: JSON.stringify({ code, pin }) })
        .then(data => {
            localStorage.setItem('kisnet.token', data.token);
            state.token = data.token;
            state.employee = data.employee;

            const returnTo = localStorage.getItem('kisnet.returnTo');
            localStorage.removeItem('kisnet.returnTo');
            const role = data.employee.role;
            goTo(returnTo && canVisit(role, returnTo.slice(1)) ? returnTo.slice(1) : stationFor(role));
        });
}

function renderCommand(root) {
    // A refresh keeps the current table on screen; only the first load shows "Loading"
    const refreshing = !!root.querySelector('#command-card');
    if (!refreshing) {
        root.innerHTML = '<div class="card" id="command-card"><h2>Command Center (Loading...)</h2></div>';
    }

    api('/api/v1/admin/on-clock')
        .then(employees => {
            const rows = employees.map(emp => `
                <tr>
                    <td>${escapeHtml(emp.code)}</td>
                    <td>${escapeHtml(emp.name)}</td>
                    <td>${escapeHtml(emp.role)}</td>
                    <td>${fmtDate(emp.clocked_in_at)}</td>
                    <td>${fmtElapsed(emp.clocked_in_at)}</td>
                    <td><button class="btn-large clock-out-btn" data-employee-id="${emp.id}">Clock Out</button></td>
                </tr>`).join('');

            root.innerHTML = `
                <div class="card" id="command-card">
                    <h2>Command Center</h2>
                    <p id="command-status" class="status-note"></p>
                    ${employees.length === 0
                        ? '<p>No employees currently on clock.</p>'
                        : `<table>
                            <thead>
                                <tr>
                                    <th>Code</th>
                                    <th>Name</th>
                                    <th>Role</th>
                                    <th>Clocked In</th>
                                    <th>Elapsed Time</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`}
                </div>`;

            root.querySelectorAll('.clock-out-btn').forEach(button => {
                button.addEventListener('click', function() {
                    const employeeId = this.dataset.employeeId;
                    if (confirm('Are you sure you want to clock out this employee?')) {
                        api(`/api/v1/admin/clock-out/${employeeId}`, { method: 'POST' })
                            .then(() => renderCommand(root))
                            .catch(error => {
                                alert('Error clocking out employee: ' + error.message);
                                console.error('Error clocking out:', error);
                            });
                    }
                });
            });
        })
        .catch(error => {
            console.error('Error loading employees on clock:', error);
            const status = root.querySelector('#command-status');
            if (status) {
                // Keep the last list on screen; the next refresh will try again
                status.textContent = `Could not refresh (${error.message}). Retrying...`;
            } else {
                root.innerHTML = `<div class="card" id="command-card"><h2>Command Center</h2><p class="status-note">Could not load the list (${escapeHtml(error.message)}). Retrying...</p></div>`;
            }
        });

    // Refresh every 10 seconds. Replace any existing timer: renderCommand runs again on every refresh.
    if (window.KIS.commandInterval) {
        clearInterval(window.KIS.commandInterval);
    }
    window.KIS.commandInterval = setInterval(() => {
        if (window.location.hash.slice(1) === '/command') {
            renderCommand(root);
        }
    }, 10000);
}

// Reports implementation
function renderReports(root) {
    // Get today's date in YYYY-MM-DD format for default values
    const today = new Date();
    const formattedToday = today.toISOString().split('T')[0];
    
    root.innerHTML = `
        <div class="card">
            <h2>Reports</h2>
            <div class="form-group">
                <label for="report-start">Start Date:</label>
                <input type="date" id="report-start" value="${formattedToday}">
            </div>
            <div class="form-group">
                <label for="report-end">End Date:</label>
                <input type="date" id="report-end" value="${formattedToday}">
            </div>
            <button id="daily-sales-btn" class="btn-large">Daily Sales Report</button>
            <button id="food-usage-btn" class="btn-large">Food Usage Report</button>
            <div id="reports-content"></div>
        </div>
        
        <div class="card">
            <h2>Menu Admin</h2>
            <button id="download-menu-btn" class="btn-large">Download menu CSV</button>
            <div class="form-group">
                <label for="menu-import-file">Import Menu CSV:</label>
                <input type="file" id="menu-import-file" accept=".csv">
            </div>
            <div id="import-status"></div>
        </div>
    `;
    
    // Daily Sales button handler
    document.getElementById('daily-sales-btn').addEventListener('click', function() {
        const startDate = document.getElementById('report-start').value;
        const endDate = document.getElementById('report-end').value;
        
        api(`/api/v1/reports/daily-sales?start=${startDate}&end=${endDate}`)
            .then(data => {
                const tableHTML = `
                    <div class="card">
                        <h3>Daily Sales Report</h3>
                        <p><strong>Period:</strong> ${data.start} to ${data.end}</p>
                        <p><strong>Total Orders:</strong> ${data.order_count}</p>
                        <p><strong>Total Quantity:</strong> ${data.total_qty}</p>
                        <p><strong>Total Sales:</strong> $${(data.total_sales_cents / 100).toFixed(2)}</p>
                        
                        <table>
                            <thead>
                                <tr>
                                    <th>Item Name</th>
                                    <th>Category</th>
                                    <th>Quantity</th>
                                    <th>Sales ($)</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.rows.map(row => `
                                    <tr>
                                        <td>${row.name}</td>
                                        <td>${row.category}</td>
                                        <td>${row.qty}</td>
                                        <td>$${(row.sales_cents / 100).toFixed(2)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                            <tfoot>
                                <tr>
                                    <th>Total</th>
                                    <th></th>
                                    <th>${data.total_qty}</th>
                                    <th>$${(data.total_sales_cents / 100).toFixed(2)}</th>
                                </tr>
                            </tfoot>
                        </table>
                    </div>
                `;
                
                document.getElementById('reports-content').innerHTML = tableHTML;
            })
            .catch(error => {
                alert('Error generating daily sales report: ' + error.message);
                console.error('Error generating daily sales report:', error);
            });
    });
    
    // Food Usage button handler
    document.getElementById('food-usage-btn').addEventListener('click', function() {
        const startDate = document.getElementById('report-start').value;
        const endDate = document.getElementById('report-end').value;
        
        api(`/api/v1/reports/food-usage?start=${startDate}&end=${endDate}`)
            .then(data => {
                const tableHTML = `
                    <div class="card">
                        <h3>Food Usage Report</h3>
                        <p><strong>Period:</strong> ${data.start} to ${data.end}</p>
                        
                        <table>
                            <thead>
                                <tr>
                                    <th>Ingredient</th>
                                    <th>Unit</th>
                                    <th>Quantity</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${data.rows.map(row => `
                                    <tr>
                                        <td>${row.ingredient}</td>
                                        <td>${row.unit}</td>
                                        <td>${parseFloat(row.qty).toFixed(2)}</td>
                                    </tr>
                                `).join('')}
                            </tbody>
                        </table>
                    </div>
                `;
                
                document.getElementById('reports-content').innerHTML = tableHTML;
            })
            .catch(error => {
                alert('Error generating food usage report: ' + error.message);
                console.error('Error generating food usage report:', error);
            });
    });
    
    // Download menu CSV button
    document.getElementById('download-menu-btn').addEventListener('click', function() {
        api('/api/v1/menu/export')
            .then(response => response.text())
            .then(text => {
                const blob = new Blob([text], { type: 'text/csv' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = 'menu-export.csv';
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);
            })
            .catch(error => {
                alert('Error exporting menu: ' + error.message);
                console.error('Error exporting menu:', error);
            });
    });
    
    // Menu import file handler
    document.getElementById('menu-import-file').addEventListener('change', function(event) {
        const file = event.target.files[0];
        if (!file) return;
        
        const reader = new FileReader();
        reader.onload = function(e) {
            const text = e.target.result;
            
            api('/api/v1/menu/import', {
                method: 'POST',
                body: text,
                headers: {
                    'Content-Type': 'text/csv'
                }
            })
            .then(data => {
                document.getElementById('import-status').innerHTML = `
                    <div class="card">
                        <h3>Import Successful</h3>
                        <p>Items imported: ${data.items}</p>
                        <p>Recipe lines imported: ${data.recipe_lines}</p>
                    </div>
                `;
            })
            .catch(error => {
                document.getElementById('import-status').innerHTML = `
                    <div class="card">
                        <h3>Import Failed</h3>
                        <p>Error: ${error.message}</p>
                    </div>
                `;
                console.error('Error importing menu:', error);
            });
        };
        reader.readAsText(file);
    });
}

// Host screen implementation
// Pop-up box used by the Host screen. Returns the body element to fill.
function openModal(title, bodyHtml) {
    closeModal();
    const overlay = document.createElement('div');
    overlay.id = 'modal-overlay';
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal" role="dialog" aria-modal="true">
            <div class="modal-header">
                <h2>${escapeHtml(title)}</h2>
                <button id="modal-close" class="modal-x" aria-label="Close">&times;</button>
            </div>
            <div id="modal-body">${bodyHtml}</div>
        </div>`;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(); });
    overlay.querySelector('#modal-close').addEventListener('click', closeModal);
    document.body.appendChild(overlay);
    return overlay.querySelector('#modal-body');
}

function closeModal() {
    const overlay = document.getElementById('modal-overlay');
    if (overlay) overlay.remove();
}

// Host screen: the 16 table seats (A1-D4). Clicking a table opens a pop-up to assign or view it.
function renderHost(root) {
    Promise.all([api('/api/v1/seats'), api('/api/v1/employees?role=server')])
        .then(([seats, servers]) => {
            const tables = seats.filter(seat => !seat.seat.startsWith('Z'));
            root.innerHTML = `
                <div class="card">
                    <h2>Host Station - Tables</h2>
                    <div class="grid-buttons host-grid">
                        ${tables.map(seat => `
                            <button class="button-card" data-seat="${seat.seat}">
                                ${seat.seat}<br>
                                ${seat.party ? escapeHtml(seat.party.party_name) + '<br>' + fmtElapsed(seat.party.opened_at) : 'Empty'}
                            </button>
                        `).join('')}
                    </div>
                </div>
            `;

            root.querySelectorAll('.host-grid button').forEach(button => {
                button.addEventListener('click', () => {
                    const seat = tables.find(item => item.seat === button.dataset.seat);
                    if (seat.party) {
                        showOccupiedTable(root, seat.party.id);
                    } else {
                        showAssignTable(root, seat.seat, servers);
                    }
                });
            });
        })
        .catch(error => {
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${escapeHtml(error.message)}</p></div>`;
            console.error('Error loading seats:', error);
        });
}

// Pop-up for an empty table: assign a party and server
function showAssignTable(root, seat, servers) {
    if (servers.length === 0) {
        openModal(`Table ${seat}`, '<p>No servers are set up yet.</p>');
        return;
    }
    const body = openModal(`Assign table ${seat}`, `
        <div class="form-group">
            <label for="party-name">Party Name</label>
            <input type="text" id="party-name" placeholder="Enter party name">
        </div>
        <div class="form-group">
            <label for="party-size">Party Size</label>
            <input type="number" id="party-size" min="1" value="2">
        </div>
        <div class="form-group">
            <label for="server-select">Assigned Server</label>
            <select id="server-select">
                ${servers.map(server => `<option value="${server.id}">${escapeHtml(server.name)}</option>`).join('')}
            </select>
        </div>
        <button id="assign-btn" class="btn-large">Assign table</button>
        <button id="cancel-assign-btn" class="btn-large">Cancel</button>
    `);

    body.querySelector('#cancel-assign-btn').addEventListener('click', closeModal);
    body.querySelector('#assign-btn').addEventListener('click', () => {
        const partyName = body.querySelector('#party-name').value.trim();
        const partySize = parseInt(body.querySelector('#party-size').value, 10);
        const serverId = parseInt(body.querySelector('#server-select').value, 10);
        if (!partyName || !(partySize >= 1)) {
            alert('Enter a party name and a size of 1 or more');
            return;
        }
        api('/api/v1/parties', {
            method: 'POST',
            body: JSON.stringify({ seat, party_name: partyName, party_size: partySize, server_id: serverId })
        })
        .then(() => {
            closeModal();
            renderHost(root);
        })
        .catch(error => alert('Could not assign table: ' + error.message));
    });
}

// Pop-up for a table that already has a party: details and close
function showOccupiedTable(root, partyId) {
    api(`/api/v1/parties/${partyId}`)
        .then(party => {
            const order = party.open_order;
            const itemCount = order ? order.items.filter(item => !item.voided).reduce((sum, item) => sum + item.qty, 0) : 0;
            const status = order ? `Order open, ${itemCount} item${itemCount === 1 ? '' : 's'}` : 'Seated, no order yet';
            const lines = order
                ? order.items.filter(item => !item.voided).map(item => `
                    <tr>
                        <td>${escapeHtml(item.name)}</td>
                        <td>${item.qty}</td>
                        <td>$${(item.line_total_cents / 100).toFixed(2)}</td>
                    </tr>`).join('')
                : '';
            const body = openModal(`Table ${party.seat}`, `
                <p><strong>${escapeHtml(party.party_name)}</strong>, party of ${party.party_size}</p>
                <p>Server: ${escapeHtml(party.server_name || 'none')}</p>
                <p>Seated: ${fmtDate(party.opened_at)} (${fmtElapsed(party.opened_at)} ago)</p>
                <p><strong>Status:</strong> ${status}</p>
                ${order ? `
                    <table class="data-table">
                        <thead><tr><th>Item</th><th>Qty</th><th>Amount</th></tr></thead>
                        <tbody>${lines || '<tr><td colspan="3">No items</td></tr>'}</tbody>
                        <tfoot><tr><th colspan="2">Current check</th><th>$${(order.total_cents / 100).toFixed(2)}</th></tr></tfoot>
                    </table>` : '<p><strong>Current check:</strong> $0.00</p>'}
                <button id="close-table-btn" class="btn-large">Close table</button>
                <button id="done-table-btn" class="btn-large">Done</button>
            `);
            body.querySelector('#done-table-btn').addEventListener('click', closeModal);
            body.querySelector('#close-table-btn').addEventListener('click', () => {
                api(`/api/v1/parties/${party.id}/close`, { method: 'POST' })
                    .then(() => {
                        closeModal();
                        renderHost(root);
                    })
                    .catch(error => alert('Could not close table: ' + error.message));
            });
        })
        .catch(error => alert('Error loading table: ' + error.message));
}

// Server screen implementation
function renderServer(root) {
    api('/api/v1/parties?open=true')
        .then(openParties => {
            root.innerHTML = `
                <div class="card">
                    <h2>Server Station</h2>
                    <div class="form-group">
                        <label for="party-select">Select Party:</label>
                        <select id="party-select" class="form-group">
                            <option value="">-- Select a party --</option>
                            ${openParties.map(party => `
                                <option value="${party.id}">${party.seat} - ${party.party_name}</option>
                            `).join('')}
                        </select>
                    </div>
                    <div id="party-details"></div>
                </div>
            `;
            
            // Add event listener to select
            document.getElementById('party-select').addEventListener('change', function() {
                const partyId = this.value;
                if (partyId) {
                    api(`/api/v1/parties/${partyId}`)
                        .then(party => {
                            renderPartyDetails(root, party, 'server');
                        })
                        .catch(error => {
                            alert('Error loading party details: ' + error.message);
                        });
                } else {
                    document.getElementById('party-details').innerHTML = '';
                }
            });
        })
        .catch(error => {
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${error.message}</p></div>`;
            console.error('Error loading open parties:', error);
        });
}

// Bar screen implementation
function renderBar(root) {
    api('/api/v1/seats')
        .then(seats => {
            // Filter for bar seats only (Z1-Z10)
            const barSeats = seats.filter(seat => seat.seat.startsWith('Z'));
            
            root.innerHTML = `
                <div class="card">
                    <h2>Bar Station</h2>
                    <div class="grid-buttons" id="bar-seats-grid">
                        ${barSeats.map(seat => `
                            <button 
                                class="button-card"
                                data-seat="${seat.seat}" 
                                data-occupied="${!!seat.party}"
                                ${seat.party ? 'disabled' : ''}
                            >
                                ${seat.seat}<br>
                                ${seat.party ? seat.party.party_name + '<br>' + fmtElapsed(seat.party.opened_at) : 'Empty'}
                            </button>
                        `).join('')}
                    </div>
                </div>
                <div id="bar-tickets-container">
                    <h3>Bar Tickets</h3>
                    <div id="bar-tickets-list"></div>
                </div>
            `;
            
            // Add event listeners to buttons
            document.querySelectorAll('#bar-seats-grid button').forEach(button => {
                button.addEventListener('click', function() {
                    const seat = this.dataset.seat;
                    const occupied = this.dataset.occupied === 'true';
                    
                    if (occupied) {
                        // Show party details for occupied seat
                        api(`/api/v1/parties/${seat.party.id}`)
                            .then(party => {
                                renderPartyDetails(root, party, 'bartender');
                            })
                            .catch(error => {
                                alert('Error loading party details: ' + error.message);
                            });
                    } else {
                        // Show create party form for empty seat
                        showCreatePartyForm(root, seat);
                    }
                });
            });
            
            // Load bar tickets
            loadBarTickets();
        })
        .catch(error => {
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${error.message}</p></div>`;
            console.error('Error loading bar seats:', error);
        });
}

// Load and display bar tickets
function loadBarTickets() {
    const barTicketsContainer = document.getElementById('bar-tickets-list');
    if (!barTicketsContainer) return;
    
    api('/api/v1/tickets?track=bar')
        .then(tickets => {
            if (tickets.length === 0) {
                barTicketsContainer.innerHTML = '<p>No active bar tickets</p>';
                return;
            }
            
            // Create a grid for tickets
            barTicketsContainer.innerHTML = `
                <div class="grid-buttons">
                    ${tickets.map(ticket => `
                        <div class="card ticket-card">
                            <p><strong>Seat:</strong> ${ticket.seat}</p>
                            <p><strong>Party:</strong> ${ticket.party_name}</p>
                            <p><strong>Opened:</strong> ${fmtElapsed(ticket.opened_at)}</p>
                            <button class="btn-large bump-btn" data-order-id="${ticket.order_id}">Bump</button>
                        </div>
                    `).join('')}
                </div>
            `;
            
            // Add event listeners to bump buttons
            document.querySelectorAll('.bump-btn').forEach(button => {
                button.addEventListener('click', function() {
                    const orderId = this.dataset.orderId;
                    api(`/api/v1/tickets/${orderId}/bar/bump`, { method: 'POST' })
                        .then(() => {
                            // Reload tickets after bump
                            loadBarTickets();
                        })
                        .catch(error => {
                            alert('Error bumping ticket: ' + error.message);
                            console.error('Error bumping ticket:', error);
                        });
                });
            });
        })
        .catch(error => {
            barTicketsContainer.innerHTML = `<p>Error loading tickets: ${error.message}</p>`;
            console.error('Error loading bar tickets:', error);
        });
}

// Kitchen screen implementation
function renderKitchen(root) {
    // Define the three columns for kitchen view
    const categories = ['appetizers', 'hot', 'cold'];
    
    root.innerHTML = `
        <div class="card">
            <h2>Kitchen Station</h2>
            <div class="grid-buttons" id="kitchen-columns">
                ${categories.map(category => `
                    <div class="kitchen-column">
                        <h3>${category.charAt(0).toUpperCase() + category.slice(1)}</h3>
                        <div id="${category}-tickets"></div>
                    </div>
                `).join('')}
            </div>
        </div>
    `;
    
    // Load tickets for each column with refresh
    categories.forEach(category => {
        loadKitchenTickets(category);
    });
    
    // Store the interval ID to clear it when leaving this screen
    window.KIS.kitchenInterval = setInterval(() => {
        categories.forEach(category => {
            loadKitchenTickets(category);
        });
    }, 2000); // Refresh every 2 seconds
}

// Load and display kitchen tickets for a specific track
function loadKitchenTickets(track) {
    const container = document.getElementById(`${track}-tickets`);
    if (!container) return;
    
    api(`/api/v1/tickets?track=${track}`)
        .then(tickets => {
            if (tickets.length === 0) {
                container.innerHTML = '<p>No active tickets</p>';
                return;
            }
            
            // Display tickets in a grid
            container.innerHTML = `
                <div class="grid-buttons">
                    ${tickets.map(ticket => `
                        <div class="card ticket-card">
                            <p><strong>Seat:</strong> ${ticket.seat}</p>
                            <p><strong>Party:</strong> ${ticket.party_name}</p>
                            <p><strong>Opened:</strong> ${fmtElapsed(ticket.opened_at)}</p>
                            <div class="order-items">
                                ${ticket.items.map(item => {
                                    const statusBadge = item.voided ? 'VOID' : item.changed ? 'CHANGED' : 'NEW';
                                    const statusClass = item.voided ? 'voided-badge' : item.changed ? 'changed-badge' : 'new-badge';
                                    return `
                                        <div class="order-item-card">
                                            <p><strong>${item.name}</strong> - Qty: ${item.qty} 
                                                ${item.notes ? ` | Notes: ${item.notes}` : ''}
                                            </p>
                                            <span class="${statusClass}">${statusBadge}</span>
                                            <p>Price: $${(item.unit_price_cents / 100).toFixed(2)}</p>
                                        </div>
                                    `;
                                }).join('')}
                            </div>
                            <button class="btn-large bump-btn" data-order-id="${ticket.order_id}" data-track="${track}">Bump</button>
                        </div>
                    `).join('')}
                </div>
            `;
            
            // Add event listeners to bump buttons
            document.querySelectorAll(`.bump-btn[data-track="${track}"]`).forEach(button => {
                button.addEventListener('click', function() {
                    const orderId = this.dataset.orderId;
                    const track = this.dataset.track;
                    api(`/api/v1/tickets/${orderId}/${track}/bump`, { method: 'POST' })
                        .then(() => {
                            // Reload tickets after bump
                            loadKitchenTickets(track);
                        })
                        .catch(error => {
                            alert('Error bumping ticket: ' + error.message);
                            console.error('Error bumping ticket:', error);
                        });
                });
            });
        })
        .catch(error => {
            container.innerHTML = `<p>Error loading ${track} tickets: ${error.message}</p>`;
            console.error(`Error loading ${track} tickets:`, error);
        });
}

// Screen map
const SCREENS = {
    '/login': renderLogin,
    '/command': renderCommand,
    '/reports': renderReports,
    '/host': renderHost,
    '/server': renderServer,
    '/bar': renderBar,
    '/kitchen': renderKitchen,
    '/timecard': renderTimeCard,
    '/home': renderHome
};

// Home: default landing page; clock in from Login
function renderHome(root) {
    root.innerHTML = `
        <div class="card">
            <h2>KISnet POS</h2>
            <p>Welcome. Use <strong>Login</strong> to clock in and open your station. Your hours and Clock Out are on the <strong>Time Card</strong>.</p>
            <button id="home-login-btn" class="btn-large">Go to Login</button>
        </div>`;
    root.querySelector('#home-login-btn').addEventListener('click', () => goTo('/login'));
}

// Time card: the signed-in employee's entries for one week, with a clock-out button.
// Admins also see every employee's total for the week.
let timecardWeek = null; // any day in the week on screen; null = this week

function isoDay(date) {
    const pad = n => String(n).padStart(2, '0');
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function shiftWeek(weekStart, weeks) {
    const base = weekStart ? new Date(weekStart + 'T00:00:00') : new Date();
    base.setDate(base.getDate() + 7 * weeks);
    return isoDay(base);
}

function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function renderTimeCard(root) {
    if (!state.employee) {
        root.innerHTML = `
            <div class="card">
                <h2>Time Card</h2>
                <p>Log in to see your time card.</p>
                <button id="tc-login-btn" class="btn-large">Go to Login</button>
            </div>`;
        root.querySelector('#tc-login-btn').addEventListener('click', () => goTo('/login'));
        return;
    }
    root.innerHTML = '<div class="card"><h2>Time Card (Loading...)</h2></div>';
    const query = timecardWeek ? `?week=${timecardWeek}` : '';
    const isAdmin = state.employee && state.employee.role === 'admin';

    Promise.all([
        api(`/api/v1/timecard${query}`),
        isAdmin ? api(`/api/v1/timecard/summary${query}`) : Promise.resolve(null)
    ])
    .then(([card, summary]) => {
        timecardWeek = card.week_start;
        root.innerHTML = '';
        root.appendChild(buildTimeCard(root, card, summary));
    })
    .catch(error => {
        root.innerHTML = `<div class="card"><h2>Time Card</h2><p>Error loading time card: ${escapeHtml(error.message)}</p></div>`;
    });
}

function buildTimeCard(root, card, summary) {
    const wrap = document.createElement('div');
    const entryRows = card.entries.map(entry => `
        <tr>
            <td>${fmtDate(entry.clocked_in_at)}</td>
            <td>${entry.clocked_out_at ? fmtDate(entry.clocked_out_at) : '<em>On clock</em>'}</td>
            <td>${entry.hours.toFixed(2)}</td>
        </tr>`).join('') || '<tr><td colspan="3">No time recorded this week</td></tr>';

    wrap.innerHTML = `
        <div class="card">
            <h2>Time Card: ${escapeHtml(card.employee.name)} (${escapeHtml(card.employee.role)})</h2>
            <div class="week-nav">
                <button id="tc-prev" class="btn-large">&larr; Previous week</button>
                <span>Week of ${card.week_start} to ${card.week_end}</span>
                <button id="tc-this" class="btn-large">This week</button>
                <button id="tc-next" class="btn-large">Next week &rarr;</button>
            </div>
            <table class="data-table">
                <thead><tr><th>Clocked in</th><th>Clocked out</th><th>Hours</th></tr></thead>
                <tbody>${entryRows}</tbody>
                <tfoot><tr><th colspan="2">Total this week</th><th>${card.total_hours.toFixed(2)}</th></tr></tfoot>
            </table>
            <button id="tc-clock-out" class="btn-large">Clock Out</button>
        </div>`;

    if (summary) {
        const summaryRows = summary.rows.map(row => `
            <tr>
                <td>${escapeHtml(row.name)}</td>
                <td>${escapeHtml(row.code)}</td>
                <td>${escapeHtml(row.role)}</td>
                <td>${row.on_clock ? 'On clock' : ''}</td>
                <td>${row.total_hours.toFixed(2)}</td>
            </tr>`).join('') || '<tr><td colspan="5">No employee worked this week</td></tr>';
        const summaryCard = document.createElement('div');
        summaryCard.innerHTML = `
            <div class="card">
                <h2>All employees, week of ${summary.week_start}</h2>
                <table class="data-table">
                    <thead><tr><th>Name</th><th>Code</th><th>Role</th><th>Status</th><th>Hours</th></tr></thead>
                    <tbody>${summaryRows}</tbody>
                </table>
            </div>`;
        wrap.appendChild(summaryCard);
    }

    wrap.querySelector('#tc-prev').addEventListener('click', () => { timecardWeek = shiftWeek(card.week_start, -1); renderTimeCard(root); });
    wrap.querySelector('#tc-next').addEventListener('click', () => { timecardWeek = shiftWeek(card.week_start, 1); renderTimeCard(root); });
    wrap.querySelector('#tc-this').addEventListener('click', () => { timecardWeek = null; renderTimeCard(root); });
    wrap.querySelector('#tc-clock-out').addEventListener('click', clockOut);
    return wrap;
}

// Logout: end this session but stay on the clock (clocking out lives on the Time Card)
function logout() {
    api('/auth/logout', { method: 'POST' })
        .catch(() => {})
        .then(() => {
            localStorage.removeItem('kisnet.token');
            localStorage.removeItem('kisnet.returnTo');
            state.employee = null;
            state.token = null;
            renderMenu();
            go('#/login');
        });
}

// Clock out function
function clockOut() {
    localStorage.removeItem('kisnet.returnTo');
    api('/auth/clock-out', { method: 'POST' })
        .then(() => {
            // Clear local storage and state
            localStorage.removeItem('kisnet.token');
            state.employee = null;
            state.token = null;
            renderMenu();
            
            // Go back to login
            go('#/login');
        })
        .catch(error => {
            console.error('Clock out error:', error);
            // Still redirect to login even if clock-out failed
            localStorage.removeItem('kisnet.token');
            state.employee = null;
            state.token = null;
            go('#/login');
        });
}

// Navigation bar for authenticated screens
function renderNavBar() {
    const topBar = document.createElement('div');
    topBar.className = 'top-bar';
    
    if (state.employee) {
        topBar.innerHTML = `
            <div>Welcome, ${state.employee.name} (${state.employee.role})</div>
            <button id="logout-btn" class="btn-large">Logout</button>
        `;
        
        document.getElementById('app').prepend(topBar);
        
        // Add event listener for clock out button
        document.getElementById('logout-btn').addEventListener('click', logout);
    } else {
        topBar.innerHTML = '<div>KISnet POS</div>';
        document.getElementById('app').prepend(topBar);
    }
}

// Update screen based on hash
// Screens a logged-out visitor may open
const PUBLIC_PATHS = ['/home', '/login', '/timecard'];

// Menu labels for every screen the menu can open
const MENU_LABELS = {
    '/home': 'Home', '/login': 'Login',
    '/command': 'Command Center', '/reports': 'Reports', '/host': 'Host', '/server': 'Server',
    '/bar': 'Bar', '/kitchen': 'Kitchen', '/timecard': 'Time Card'
};

// The three-bar menu sits outside the screens, so it is available on every page
function buildMenuChrome() {
    document.body.insertAdjacentHTML('beforeend', `
        <button id="menu-toggle" class="menu-toggle" aria-label="Open menu">&#9776;</button>
        <div id="menu-backdrop" class="menu-backdrop"></div>
        <nav id="side-menu" class="side-menu"></nav>`);
    document.getElementById('menu-toggle').addEventListener('click', () => toggleMenu(!isMenuOpen()));
    document.getElementById('menu-backdrop').addEventListener('click', () => toggleMenu(false));
}

function isMenuOpen() {
    return document.getElementById('side-menu').classList.contains('open');
}

function toggleMenu(open) {
    document.getElementById('side-menu').classList.toggle('open', open);
    document.getElementById('menu-backdrop').classList.toggle('open', open);
}

// Menu options depend on who is signed in; logged-out users see Login
function renderMenu() {
    const menu = document.getElementById('side-menu');
    if (!menu) return;
    let paths;
    if (!state.employee) {
        paths = ['/home', '/login', '/timecard'];
    } else if (state.employee.role === 'admin') {
        paths = ['/command', '/reports', '/host', '/server', '/bar', '/kitchen', '/timecard'];
    } else {
        paths = [stationFor(state.employee.role), '/timecard'];
    }
    menu.innerHTML = '<h3 class="side-menu-title">Menu</h3>';
    paths.forEach(path => {
        const link = document.createElement('a');
        link.href = `#${path}`;
        link.className = 'nav-item';
        link.textContent = MENU_LABELS[path];
        link.addEventListener('click', (e) => {
            e.preventDefault();
            toggleMenu(false);
            go(path);
        });
        menu.appendChild(link);
    });
}

function updateScreen() {
    const root = document.getElementById('app');
    if (!root) return;

    closeModal();
    stopScreenTimers();
    root.innerHTML = '';
    document.querySelectorAll('.top-bar').forEach(bar => bar.remove());
    renderMenu();

    const container = document.createElement('div');
    container.className = 'container';
    const mainContent = document.createElement('div');
    mainContent.className = 'main-content';
    container.appendChild(mainContent);
    root.appendChild(container);

    if (!state.employee) {
        // Try to resume a saved session, otherwise show the login form
        const token = localStorage.getItem('kisnet.token');
        if (token) {
            api('/auth/me')
                .then(data => {
                    state.employee = data;
                    state.token = token;
                    const current = window.location.hash.slice(1);
                    goTo(current && canVisit(data.role, current) ? current : stationFor(data.role));
                })
                .catch(() => {
                    localStorage.removeItem('kisnet.token');
                    renderLogin(mainContent);
                });
        } else {
            // Logged out: show the page asked for if it is public, otherwise the login form
            const path = window.location.hash.slice(1);
            if (PUBLIC_PATHS.includes(path)) {
                SCREENS[path](mainContent);
            } else {
                renderLogin(mainContent);
            }
        }
        return;
    }

    renderNavBar();
    const path = window.location.hash.slice(1) || '/login';
    if (!SCREENS[path]) {
        go('/login');
        return;
    }
    SCREENS[path](mainContent);
}

// Initialize the app
function init() {
    buildMenuChrome();

    // Listen for hash changes
    window.addEventListener('hashchange', updateScreen);

    // Any input counts as activity; check for idleness every 15 seconds
    ['pointerdown', 'keydown', 'mousemove', 'touchstart', 'input', 'scroll'].forEach(type =>
        document.addEventListener(type, () => { lastActivity = Date.now(); }, { passive: true }));
    setInterval(() => {
        if (localStorage.getItem('kisnet.token') && Date.now() - lastActivity > IDLE_LIMIT_MS) {
            expireSession();
        }
    }, 15000);
    
    // Initial screen load
    updateScreen();
}

// Expose to global scope for later tasks
window.KIS = {
    api,
    state,
    go,
    SCREENS,
    fmtDate,
    fmtElapsed
};

// Clear intervals when leaving kitchen screen
// Stop every screen's refresh timer (kitchen tickets, command center)
function stopScreenTimers() {
    clearKitchenInterval();
    stopTicketPanel();
    if (window.KIS && window.KIS.commandInterval) {
        clearInterval(window.KIS.commandInterval);
        window.KIS.commandInterval = null;
    }
}

function clearKitchenInterval() {
    if (window.KIS && window.KIS.kitchenInterval) {
        clearInterval(window.KIS.kitchenInterval);
        window.KIS.kitchenInterval = null;
    }
}

// Start the app when DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}
// API helper function
function api(path, opts = {}) {
    const url = path.startsWith('/api/v1') ? path : '/api/v1' + path;
    const defaultOpts = {
        headers: {
            'Content-Type': 'application/json',
        }
    };
    
    // Add Bearer token if available
    const token = sessionStorage.getItem('kisnet.token');
    if (token) {
        defaultOpts.headers['Authorization'] = `Bearer ${token}`;
    }
    
    const options = { ...defaultOpts, ...opts };
    
    return fetch(url, options)
        .then(response => {
            if (!response.ok) {
                if (response.status === 401 && !path.includes('/auth/')) {
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
    if (role === 'admin') return path in SCREENS;
    if (path === '/timecard') return true;
    if (role === 'bartender') return path === '/bar' || path === '/barseats';
    return path === stationFor(role);
}

// Idle sign-out: after this long with no input, return to login and resume the same page after signing in
const IDLE_LIMIT_MS = 5 * 60 * 1000;
let lastActivity = Date.now();

function expireSession() {
    const token = sessionStorage.getItem('kisnet.token');
    if (token) {
        fetch('/api/v1/auth/logout', { method: 'POST', headers: { Authorization: `Bearer ${token}` } }).catch(() => {});
    }
    const current = window.location.hash;
    if (current && current !== '#/login') {
        sessionStorage.setItem('kisnet.returnTo', current);
    }
    sessionStorage.removeItem('kisnet.token');
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
// Bar seat (BAR1-BAR10): only a party name. The bartender is the server; no party size is needed.
function showCreatePartyForm(root, seat) {
    root.innerHTML = `
        <div class="card">
            <h2>Seat ${escapeHtml(seat)}</h2>
            <div class="form-group">
                <label for="party-name">Party Name</label>
                <input type="text" id="party-name" placeholder="Enter party name">
            </div>
            <button id="create-party-btn" class="btn-large">Create Party</button>
            <button id="cancel-create-btn" class="btn-large">Cancel</button>
        </div>
    `;

    document.getElementById('create-party-btn').addEventListener('click', function() {
        const partyName = document.getElementById('party-name').value.trim();
        if (!partyName) {
            alert('Enter a party name');
            return;
        }
        api('/api/v1/parties', {
            method: 'POST',
            body: JSON.stringify({ seat: seat, party_name: partyName })
        })
        .then(() => renderBar(root))
        .catch(error => alert('Could not create party: ' + error.message));
    });

    document.getElementById('cancel-create-btn').addEventListener('click', () => renderBar(root));
}

function showAddItemPopover(button, item, party, root, role = 'server') {
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
        draftFor(party.id).newLines.push({
            menu_item_id: parseInt(item.id, 10),
            name: item.name,
            price_cents: item.price,
            qty,
            notes
        });
        closeItemPopover();
        drawTicketList();
        drawTicketEditor();
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

// Small pop-up beside an occupied bar seat
function showSeatPopover(button, seat, root, role = 'bartender') {
    closeItemPopover();
    const popover = document.createElement('div');
    popover.id = 'item-popover';
    popover.className = 'item-popover';
    popover.innerHTML = `
        <p><strong>${escapeHtml(seat.seat)}</strong>: ${escapeHtml(seat.party.party_name)}</p>
        <div class="item-popover-actions">
            <button id="seat-place-order" class="btn-large">Place order</button>
            <button id="seat-payment" class="btn-large">Payment</button>
            <button id="seat-cancel" class="btn-large">Cancel</button>
        </div>`;
    document.body.appendChild(popover);
    positionBeside(popover, button);

    popover.querySelector('#seat-cancel').addEventListener('click', closeItemPopover);
    popover.querySelector('#seat-place-order').addEventListener('click', () => {
        closeItemPopover();
        api(`/api/v1/parties/${seat.party.id}`)
            .then(party => renderPartyDetails(root, party, role))
            .catch(error => alert('Could not open the order: ' + error.message));
    });
    popover.querySelector('#seat-payment').addEventListener('click', () => {
        closeItemPopover();
        api(`/api/v1/parties/${seat.party.id}`)
            .then(party => {
                renderPartyDetails(root, party, role);
                confirmPayment(party, role);
            })
            .catch(error => alert('Could not open the ticket: ' + error.message));
    });
    watchOutsideClicks(popover, button);
}

// Place a pop-up to the right of the button, or to the left if there is no room
function positionBeside(popover, button) {
    const rect = button.getBoundingClientRect();
    const width = popover.offsetWidth || 220;
    const left = rect.right + 8 + width <= window.innerWidth ? rect.right + 8 : rect.left - width - 8;
    popover.style.top = `${Math.max(8, rect.top)}px`;
    popover.style.left = `${Math.max(8, left)}px`;
}

function watchOutsideClicks(popover, button) {
    const outside = (event) => {
        if (!popover.contains(event.target) && event.target !== button) {
            closeItemPopover();
        }
    };
    popover._outside = outside;
    setTimeout(() => document.addEventListener('pointerdown', outside, true), 0);
}

function closeItemPopover() {
    const popover = document.getElementById('item-popover');
    if (!popover) return;
    document.removeEventListener('pointerdown', popover._outside, true);
    popover.remove();
}

// ---- Order ticket panel. Nothing is saved until Send: new lines, changes and voids are staged in the browser ----

const TICKET_REFRESH_MS = 3000;

// Staged (unsent) changes, kept per party so they survive the panel refreshing
function draftFor(partyId) {
    window.KIS.drafts = window.KIS.drafts || {};
    if (!window.KIS.drafts[partyId]) {
        window.KIS.drafts[partyId] = { newLines: [], edits: {}, voids: {} };
    }
    return window.KIS.drafts[partyId];
}

function hasStagedChanges(draft) {
    return draft.newLines.length > 0 || Object.keys(draft.edits).length > 0 || Object.values(draft.voids).some(Boolean);
}

function sameKey(a, b) {
    return !!a && !!b && a.kind === b.kind && (a.kind === 'sent' ? a.id === b.id : a.index === b.index);
}

function showTicketPanel(party) {
    window.KIS.ticket = window.KIS.ticket || { partyId: null, selectedKey: null, party: null, interval: null };
    const ticket = window.KIS.ticket;
    if (ticket.partyId !== party.id) {
        ticket.selectedKey = null;
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
            <div id="ticket-editor" class="ticket-editor"></div>
            <div class="ticket-send-bar">
                <p id="ticket-total" class="ticket-total"></p>
                <button id="ticket-send" class="btn-large">Send</button>
                ${['server', 'bartender'].includes(state.employee && state.employee.role)
                    ? '<button id="ticket-payment" class="btn-large">Send to Payment</button>' : ''}
            </div>`;
        document.body.appendChild(panel);
        document.body.classList.add('ticket-open');

        document.getElementById('ticket-list').addEventListener('click', (event) => {
            const row = event.target.closest('.ticket-row');
            if (!row) return;
            const key = row.dataset.kind === 'sent'
                ? { kind: 'sent', id: parseInt(row.dataset.id, 10) }
                : { kind: 'new', index: parseInt(row.dataset.index, 10) };
            window.KIS.ticket.selectedKey = key;
            drawTicketList();
            drawTicketEditor();
        });
        document.getElementById('ticket-send').addEventListener('click', sendTicket);
        const payment = document.getElementById('ticket-payment');
        if (payment) payment.addEventListener('click', sendToPayment);
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

// Reload the party's sent items. Staged changes are kept; only the server copy is refreshed.
function refreshTicketPanel() {
    const ticket = window.KIS.ticket;
    if (!ticket || !ticket.partyId || !document.getElementById('ticket-panel')) return;
    api(`/api/v1/parties/${ticket.partyId}`)
        .then(party => {
            ticket.party = party;
            drawTicketList();
            if (ticket.selectedKey && !currentLine()) {
                ticket.selectedKey = null;
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

function sentItems() {
    const party = window.KIS.ticket && window.KIS.ticket.party;
    return party && party.open_order ? party.open_order.items : [];
}

// The line the user is working on, as it would be sent
function currentLine() {
    const ticket = window.KIS.ticket;
    const key = ticket && ticket.selectedKey;
    if (!key) return null;
    const draft = draftFor(ticket.partyId);
    if (key.kind === 'new') {
        const line = draft.newLines[key.index];
        return line ? { key, name: line.name, qty: line.qty, notes: line.notes, price: line.price_cents, locked: false, voided: false, isNew: true } : null;
    }
    const item = sentItems().find(entry => entry.id === key.id);
    if (!item) return null;
    const edit = draft.edits[item.id] || {};
    return {
        key,
        name: item.name,
        qty: edit.qty !== undefined ? edit.qty : item.qty,
        notes: edit.notes !== undefined ? edit.notes : item.notes,
        price: item.unit_price_cents,
        locked: !!item.bumped || !!item.voided,
        voided: !!item.voided,
        isNew: false,
        staged: !!draft.voids[item.id]
    };
}

function drawTicketList() {
    const ticket = window.KIS.ticket;
    const list = document.getElementById('ticket-list');
    if (!list || !ticket || !ticket.party) return;
    const draft = draftFor(ticket.partyId);
    const party = ticket.party;
    document.getElementById('ticket-title').textContent = `Ticket: ${party.seat} - ${party.party_name}`;

    const rows = [];
    let total = 0;
    sentItems().forEach(item => {
        const edit = draft.edits[item.id] || {};
        const qty = edit.qty !== undefined ? edit.qty : item.qty;
        const notes = edit.notes !== undefined ? edit.notes : item.notes;
        const removedNow = !!draft.voids[item.id];
        const voided = item.voided || removedNow;
        const lineTotal = voided ? 0 : item.unit_price_cents * qty;
        total += lineTotal;
        const badges = [];
        if (item.voided) badges.push('VOID');
        else if (removedNow) badges.push('REMOVE ON SEND');
        else if (item.bumped) badges.push('SENT');
        if (!voided && (edit.qty !== undefined || edit.notes !== undefined)) badges.push('EDITED');
        rows.push(ticketRow({ kind: 'sent', id: item.id }, item.name, qty, notes, lineTotal, badges, voided, ticket.selectedKey, !voided));
    });
    draft.newLines.forEach((line, index) => {
        const lineTotal = line.price_cents * line.qty;
        total += lineTotal;
        rows.push(ticketRow({ kind: 'new', index }, line.name, line.qty, line.notes, lineTotal, ['NEW'], false, ticket.selectedKey));
    });

    list.innerHTML = rows.length ? rows.join('') : '<p>No items yet. Add items from the menu.</p>';
    document.getElementById('ticket-total').textContent = `Total: $${(total / 100).toFixed(2)}`;
    document.getElementById('ticket-send').disabled = !hasStagedChanges(draft);
}

function ticketRow(key, name, qty, notes, lineTotal, badges, voided, selectedKey, isSent = false) {
    const attrs = key.kind === 'sent' ? `data-kind="sent" data-id="${key.id}"` : `data-kind="new" data-index="${key.index}"`;
    return `
        <div class="ticket-row ${sameKey(key, selectedKey) ? 'selected' : ''} ${voided ? 'voided' : ''} ${isSent ? 'sent' : ''}" ${attrs}>
            <strong>${escapeHtml(name)}</strong> x${qty}
            <span class="ticket-price">$${(lineTotal / 100).toFixed(2)}</span>
            ${badges.map(b => `<span class="ticket-badge${b === 'SENT' ? ' sent-badge' : ''}">${b}</span>`).join('')}
            ${notes ? `<div class="ticket-notes">${escapeHtml(notes)}</div>` : ''}
        </div>`;
}

// Editor for the selected line. Staging only: the change is kept in the browser until Send.
function drawTicketEditor() {
    const editor = document.getElementById('ticket-editor');
    if (!editor) return;
    const line = currentLine();
    if (!line) {
        editor.innerHTML = '<p class="ticket-hint">Select an item to change it before you send.</p>';
        return;
    }
    const disabled = line.locked ? 'disabled' : '';
    const removeLabel = line.staged ? 'Keep item' : (line.isNew ? 'Remove' : 'Remove on send');
    editor.innerHTML = `
        <h4>${escapeHtml(line.name)}</h4>
        ${line.locked ? '<p class="status-note">Already at the kitchen or bar, so it cannot be changed.</p>' : ''}
        <div class="qty-row">
            <button id="tk-dec" ${disabled}>-</button>
            <input id="tk-qty" type="number" min="1" value="${line.qty}" ${disabled}>
            <button id="tk-inc" ${disabled}>+</button>
        </div>
        <input id="tk-notes" type="text" placeholder="Notes" value="${escapeHtml(line.notes || '')}" ${disabled}>
        <div class="ticket-editor-actions">
            <button id="tk-update" class="btn-large" ${disabled}>Update line</button>
            <button id="tk-remove" class="btn-large" ${line.locked ? 'disabled' : ''}>${removeLabel}</button>
        </div>`;

    const qtyInput = document.getElementById('tk-qty');
    if (!line.locked) {
        document.getElementById('tk-dec').addEventListener('click', () => {
            qtyInput.value = Math.max(1, (parseInt(qtyInput.value, 10) || 1) - 1);
        });
        document.getElementById('tk-inc').addEventListener('click', () => {
            qtyInput.value = (parseInt(qtyInput.value, 10) || 0) + 1;
        });
        document.getElementById('tk-update').addEventListener('click', () => updateSelectedLine(line));
    }
    document.getElementById('tk-remove').addEventListener('click', () => toggleSelectedLine(line));
}

function updateSelectedLine(line) {
    const qty = parseInt(document.getElementById('tk-qty').value, 10);
    const notes = document.getElementById('tk-notes').value.trim();
    if (!(qty >= 1)) {
        alert('Quantity must be at least 1');
        return;
    }
    const draft = draftFor(window.KIS.ticket.partyId);
    if (line.isNew) {
        draft.newLines[line.key.index].qty = qty;
        draft.newLines[line.key.index].notes = notes || null;
    } else {
        draft.edits[line.key.id] = { qty, notes };
    }
    drawTicketList();
    drawTicketEditor();
}

function toggleSelectedLine(line) {
    const ticket = window.KIS.ticket;
    const draft = draftFor(ticket.partyId);
    if (line.isNew) {
        draft.newLines.splice(line.key.index, 1);
        ticket.selectedKey = null;
    } else {
        // Removing a sent line is staged too; "Keep item" undoes it before Send
        if (draft.voids[line.key.id]) {
            delete draft.voids[line.key.id];
        } else {
            draft.voids[line.key.id] = true;
        }
    }
    drawTicketList();
    drawTicketEditor();
}

// Payment: asks for confirmation, then closes the table (payment is assumed accepted)
function confirmPayment(party, role) {
    const draft = draftFor(party.id);
    const warning = hasStagedChanges(draft) ? '<p class="status-note">Changes that have not been sent will be lost.</p>' : '';
    const body = openModal('Send to payment', `
        <p><strong>${escapeHtml(party.seat)}</strong> - ${escapeHtml(party.party_name)}</p>
        <p>Send this table to payment? The table will close.</p>
        ${warning}
        <button id="payment-confirm-btn" class="btn-large">Confirm payment</button>
        <button id="payment-cancel-btn" class="btn-large">Cancel</button>`);
    body.querySelector('#payment-cancel-btn').addEventListener('click', closeModal);
    body.querySelector('#payment-confirm-btn').addEventListener('click', () => {
        closeModal();
        api(`/api/v1/parties/${party.id}/close`, { method: 'POST' })
            .then(() => {
                window.KIS.drafts[party.id] = null;
                stopTicketPanel();
                window.KIS.ticket.partyId = null;
                goTo(role === 'bartender' ? '/barseats' : '/server');
            })
            .catch(error => alert('Could not send to payment: ' + error.message));
    });
}

// Send to Payment in the order sidebar
function sendToPayment() {
    const party = window.KIS.ticket.party;
    confirmPayment(party, state.employee.role);
}

// Send: everything staged goes to the server in one request, then to the kitchen and bar
function sendTicket() {
    const ticket = window.KIS.ticket;
    const draft = draftFor(ticket.partyId);
    if (!hasStagedChanges(draft)) return;

    const body = {
        items: draft.newLines.map(line => ({ menu_item_id: line.menu_item_id, qty: line.qty, notes: line.notes || null })),
        updates: Object.entries(draft.edits).map(([id, edit]) => ({ item_id: parseInt(id, 10), qty: edit.qty, notes: edit.notes })),
        voids: Object.entries(draft.voids).filter(([, removed]) => removed).map(([id]) => parseInt(id, 10))
    };

    api(`/api/v1/parties/${ticket.partyId}/send`, { method: 'POST', body: JSON.stringify(body) })
        .then(() => {
            draft.newLines = [];
            draft.edits = {};
            draft.voids = {};
            ticket.selectedKey = null;
            setTicketStatus('Sent to the kitchen and bar.');
            return refreshTicketPanel();
        })
        .catch(error => alert('Could not send: ' + error.message));
}

function renderPartyDetails(root, party, role) {
    const isHostScreen = role === 'host';
    const isBarScreen = role === 'bartender';
    const isServerScreen = role === 'server' || isBarScreen;
    
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
                    ${isServerScreen ? `<button id="back-to-tables" class="btn-large">${isBarScreen ? 'Back to bar seats' : 'Back to my tables'}</button>` : ''}
                    <h2>Party Details</h2>
                    <p><strong>Seat:</strong> ${party.seat}</p>
                    <p><strong>Party Name:</strong> ${party.party_name}</p>
                    <p><strong>Party Size:</strong> ${party.party_size}</p>
                    <p><strong>Server:</strong> ${party.server_name || 'None'}</p>
                    <p><strong>Started:</strong> ${fmtDate(party.opened_at)}</p>
                    <p><strong>Elapsed:</strong> ${fmtElapsed(party.opened_at)} minutes</p>
                    
                    ${isHostScreen && party.closed_at ? 
                        `<p><strong>Closed:</strong> ${fmtDate(party.closed_at)}</p>` : ''}
                        
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
            
            if (isServerScreen) {
                document.getElementById('back-to-tables').addEventListener('click', () => (isBarScreen ? renderBar(root) : renderServer(root)));
            }

            // Clicking a menu item asks, in a small pop-up beside it, whether to add it
            if (isServerScreen && !party.closed_at) {
                document.querySelectorAll('.menu-item-btn').forEach(button => {
                    button.addEventListener('click', function() {
                        showAddItemPopover(this, { id: this.dataset.itemId, name: this.dataset.name, price: parseInt(this.dataset.price, 10) }, party, root, role);
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
                <h2>KISnet POS</h2>
                <div class="form-group">
                    <label for="employee-code">Employee Code</label>
                    <input type="text" id="employee-code" placeholder="e.g. HOST1">
                </div>
                <div class="form-group">
                    <label for="pin">PIN</label>
                    <input type="password" id="pin" placeholder="Enter your PIN">
                </div>
                <p id="login-message" class="status-note"></p>
                <button id="clock-in-btn" class="btn-large">Clock In</button>
                <button id="log-in-btn" class="btn-large">Log In</button>
            </div>
        </div>
    `;

    document.getElementById('clock-in-btn').addEventListener('click', handleClockIn);
    document.getElementById('log-in-btn').addEventListener('click', handleLogIn);
}

function loginCredentials() {
    const code = document.getElementById('employee-code').value.trim();
    const pin = document.getElementById('pin').value;
    if (!code || !pin) {
        setLoginMessage('Enter your employee code and PIN.');
        return null;
    }
    return { code, pin };
}

function setLoginMessage(text) {
    const message = document.getElementById('login-message');
    if (message) message.textContent = text;
}

// Clock In: records the shift. It does not log anyone in.
function handleClockIn() {
    const credentials = loginCredentials();
    if (!credentials) return;

    api('/auth/preview', { method: 'POST', body: JSON.stringify(credentials) })
        .then(preview => {
            if (preview.on_clock) {
                setLoginMessage(`${preview.employee.name} is already clocked in.`);
                return;
            }
            confirmClockIn(preview, credentials);
        })
        .catch(error => setLoginMessage(error.message));
}

function roleLabel(role) {
    return role.charAt(0).toUpperCase() + role.slice(1);
}

// Pop-up asking the person to confirm their clock in
function confirmClockIn(preview, credentials) {
    const employee = preview.employee;
    const positions = preview.positions || [employee.role];
    const picker = positions.length > 1
        ? `<div class="form-group">
               <label for="clock-position">Clocking in as</label>
               <select id="clock-position">
                   ${positions.map(role => `<option value="${role}">${escapeHtml(roleLabel(role))}</option>`).join('')}
               </select>
           </div>`
        : `<p><strong>Position:</strong> ${escapeHtml(roleLabel(positions[0]))}</p>`;
    const body = openModal('Confirm clock in', `
        <p><strong>Name:</strong> ${escapeHtml(employee.name)}</p>
        ${picker}
        <p><strong>Time:</strong> ${fmtDate(preview.now)}</p>
        <p>Clock in now?</p>
        <button id="confirm-clock-in-btn" class="btn-large">Confirm clock in</button>
        <button id="cancel-clock-in-btn" class="btn-large">Cancel</button>
    `);

    body.querySelector('#cancel-clock-in-btn').addEventListener('click', closeModal);
    body.querySelector('#confirm-clock-in-btn').addEventListener('click', () => {
        closeModal();
        const chosen = body.querySelector('#clock-position');
        const position = chosen ? chosen.value : positions[0];
        api('/auth/clock-in', { method: 'POST', body: JSON.stringify({ ...credentials, position }) })
            .then(result => {
                setLoginMessage(`${result.employee.name} clocked in at ${fmtDate(result.clocked_in_at)}. Log in to open your station.`);
                document.getElementById('pin').value = '';
            })
            .catch(error => setLoginMessage(error.message));
    });
}

// Log In: opens a station session. Only works for someone already on the clock.
function handleLogIn() {
    const credentials = loginCredentials();
    if (!credentials) return;

    api('/auth/login', { method: 'POST', body: JSON.stringify(credentials) })
        .then(data => {
            sessionStorage.setItem('kisnet.token', data.token);
            state.token = data.token;
            state.employee = data.employee;

            // Return to the page the user was on before sign-out, if their role may see it
            const returnTo = sessionStorage.getItem('kisnet.returnTo');
            sessionStorage.removeItem('kisnet.returnTo');
            const role = data.employee.role;
            goTo(returnTo && canVisit(role, returnTo.slice(1)) ? returnTo.slice(1) : stationFor(role));
        })
        .catch(error => setLoginMessage(error.message));
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
                </tr>`).join('');

            root.innerHTML = `
                <div class="card" id="command-card">
                    <h2>Command Center</h2>
                    <p id="command-status" class="status-note"></p>
                    <div id="stats-block"></div>
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
                                </tr>
                            </thead>
                            <tbody>${rows}</tbody>
                        </table>`}
                </div>`;

            loadDayStats();
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

// System > Employees (admin): roster with oversight information, and adding an employee
const POSITION_OPTIONS = ['admin', 'host', 'server', 'bartender', 'kitchen'];

function renderEmployees(root) {
    root.innerHTML = `
        <div class="card">
            <h2>Employees</h2>
            <div class="week-nav">
                <button id="emp-add-toggle" class="btn-large">Add employee</button>
            </div>
            <div id="emp-add-form"></div>
            <p id="emp-status" class="status-note"></p>
            <div id="emp-roster"></div>
        </div>`;
    document.getElementById('emp-add-toggle').addEventListener('click', showAddEmployeeForm);
    loadRoster();
}

function loadRoster() {
    const box = document.getElementById('emp-roster');
    if (!box) return;
    api('/api/v1/admin/roster')
        .then(rows => {
            const money = hours => `${hours.toFixed(2)} h`;
            box.innerHTML = `
                <table class="data-table">
                    <thead><tr><th>Code</th><th>Name</th><th>Positions</th><th>Hire date</th><th>SSN</th>
                        <th>On clock</th><th>Hours this week</th><th>Address</th><th>DOB</th></tr></thead>
                    <tbody>${rows.map(row => `
                        <tr>
                            <td>${escapeHtml(row.code)}</td>
                            <td>${escapeHtml(row.name)}</td>
                            <td>${row.positions.map(roleLabel).join(', ')}</td>
                            <td>${row.hire_date || ''}</td>
                            <td>${escapeHtml(row.ssn)}</td>
                            <td>${row.on_clock ? 'Yes' : ''}</td>
                            <td>${money(row.week_hours)}</td>
                            <td>${escapeHtml(row.address || '')}</td>
                            <td>${row.dob || ''}</td>
                        </tr>`).join('')}</tbody>
                </table>`;
        })
        .catch(error => {
            box.innerHTML = `<p class="status-note">Could not load the roster (${escapeHtml(error.message)}).</p>`;
        });
}

function showAddEmployeeForm() {
    const form = document.getElementById('emp-add-form');
    form.innerHTML = `
        <div class="form-group"><label for="emp-name">Name</label><input type="text" id="emp-name"></div>
        <div class="form-group"><label for="emp-address">Address</label><input type="text" id="emp-address"></div>
        <div class="form-group"><label for="emp-dob">Date of birth</label><input type="date" id="emp-dob"></div>
        <div class="form-group"><label for="emp-hire">Hire date</label><input type="date" id="emp-hire" value="${isoDay(new Date())}"></div>
        <fieldset class="form-group">
            <legend>Positions (tick every job this person can do)</legend>
            ${POSITION_OPTIONS.map(role => `
                <label class="checkbox-row"><input type="checkbox" class="emp-position" value="${role}"> ${roleLabel(role)}</label>`).join('')}
        </fieldset>
        <div class="form-group"><label for="emp-pin">PIN (4 digits or more)</label><input type="password" id="emp-pin" value="1234"></div>
        <button id="emp-save" class="btn-large">Save employee</button>
        <button id="emp-cancel" class="btn-large">Cancel</button>`;
    document.getElementById('emp-cancel').addEventListener('click', () => { form.innerHTML = ''; });
    document.getElementById('emp-save').addEventListener('click', saveEmployee);
}

function saveEmployee() {
    const positions = [...document.querySelectorAll('.emp-position:checked')].map(box => box.value);
    const name = document.getElementById('emp-name').value.trim();
    if (!name) { alert('Enter the name'); return; }
    if (positions.length === 0) { alert('Tick at least one position'); return; }
    const body = {
        name,
        address: document.getElementById('emp-address').value.trim() || null,
        dob: document.getElementById('emp-dob').value || null,
        hire_date: document.getElementById('emp-hire').value || null,
        positions,
        pin: document.getElementById('emp-pin').value
    };
    api('/api/v1/admin/employees', { method: 'POST', body: JSON.stringify(body) })
        .then(created => {
            document.getElementById('emp-add-form').innerHTML = '';
            document.getElementById('emp-status').textContent = `Added ${created.code} ${created.name}.`;
            loadRoster();
        })
        .catch(error => alert('Could not add the employee: ' + error.message));
}

// System > Recipes (admin): add a recipe with its price; its category decides where it is made
function renderRecipes(root) {
    root.innerHTML = `
        <div class="card">
            <h2>Recipes</h2>
            <h3>Add a recipe</h3>
            <div class="form-group"><label for="rec-name">Name</label><input type="text" id="rec-name"></div>
            <div class="form-group">
                <label for="rec-category">Category</label>
                <select id="rec-category">
                    <option value="bar">Bar (drinks)</option>
                    <option value="appetizers">Apps</option>
                    <option value="hot">Hot</option>
                    <option value="cold">Cold</option>
                </select>
            </div>
            <div class="form-group"><label for="rec-price">Price ($)</label><input type="number" id="rec-price" min="0" step="0.01"></div>
            <h4>Ingredients</h4>
            <div id="rec-ingredients"></div>
            <button id="rec-add-ingredient" class="btn-large">Add ingredient</button>
            <button id="rec-save" class="btn-large">Save recipe</button>
            <p id="rec-status" class="status-note"></p>
            <h3>Recipes on the menu</h3>
            <div id="rec-list"></div>
        </div>`;
    addIngredientRow();
    document.getElementById('rec-add-ingredient').addEventListener('click', addIngredientRow);
    document.getElementById('rec-save').addEventListener('click', saveRecipe);
    loadRecipeList();
}

function addIngredientRow() {
    const box = document.getElementById('rec-ingredients');
    const row = document.createElement('div');
    row.className = 'ingredient-row';
    row.innerHTML = `
        <input type="text" class="ing-name" placeholder="Ingredient">
        <input type="number" class="ing-qty" min="0" step="0.1" placeholder="Qty">
        <input type="text" class="ing-unit" placeholder="Unit (oz, each)">`;
    box.appendChild(row);
}

function saveRecipe() {
    const name = document.getElementById('rec-name').value.trim();
    const price = parseFloat(document.getElementById('rec-price').value);
    const ingredients = [...document.querySelectorAll('.ingredient-row')].map(row => ({
        ingredient: row.querySelector('.ing-name').value.trim(),
        qty: parseFloat(row.querySelector('.ing-qty').value),
        unit: row.querySelector('.ing-unit').value.trim()
    })).filter(line => line.ingredient);
    const status = document.getElementById('rec-status');
    if (!name || !(price >= 0)) { status.textContent = 'Enter a name and a price.'; return; }
    if (ingredients.some(line => !(line.qty > 0) || !line.unit)) { status.textContent = 'Each ingredient needs a quantity and a unit.'; return; }
    api('/api/v1/admin/recipes', {
        method: 'POST',
        body: JSON.stringify({ name, category: document.getElementById('rec-category').value,
                               price_cents: Math.round(price * 100), ingredients })
    })
        .then(created => {
            status.textContent = `Added ${created.name} at $${(created.price_cents / 100).toFixed(2)}.`;
            document.getElementById('rec-name').value = '';
            document.getElementById('rec-price').value = '';
            document.getElementById('rec-ingredients').innerHTML = '';
            addIngredientRow();
            loadRecipeList();
        })
        .catch(error => { status.textContent = `Could not save: ${error.message}`; });
}

function loadRecipeList() {
    const box = document.getElementById('rec-list');
    if (!box) return;
    api('/api/v1/admin/recipes')
        .then(recipes => {
            box.innerHTML = `
                <table class="data-table">
                    <thead><tr><th>Name</th><th>Category</th><th>Price</th><th>Ingredients</th></tr></thead>
                    <tbody>${recipes.map(recipe => `
                        <tr>
                            <td>${escapeHtml(recipe.name)}</td>
                            <td>${escapeHtml(roleLabel(recipe.category))}</td>
                            <td>$${(recipe.price_cents / 100).toFixed(2)}</td>
                            <td>${recipe.ingredients.map(line => `${line.qty} ${escapeHtml(line.unit)} ${escapeHtml(line.ingredient)}`).join(', ')}</td>
                        </tr>`).join('')}</tbody>
                </table>`;
        })
        .catch(error => {
            box.innerHTML = `<p class="status-note">Could not load recipes (${escapeHtml(error.message)}).</p>`;
        });
}

// Daily Summary (admin): totals for one business day, items by popularity, and the End of Day export
function renderSummary(root) {
    root.innerHTML = `
        <div class="card">
            <h2>Daily Summary</h2>
            <div class="week-nav">
                <label for="sum-date">Business day</label>
                <input type="date" id="sum-date" value="${isoDay(new Date())}">
                <button id="sum-show" class="btn-large">Show</button>
                <button id="sum-end" class="btn-large">End of Day</button>
            </div>
            <p id="sum-status" class="status-note"></p>
            <div id="sum-body"></div>
        </div>`;
    document.getElementById('sum-show').addEventListener('click', loadSummary);
    document.getElementById('sum-end').addEventListener('click', confirmEndOfDay);
    loadSummary();
}

function loadSummary() {
    const day = document.getElementById('sum-date').value;
    const body = document.getElementById('sum-body');
    Promise.all([
        api(`/api/v1/reports/summary?day=${day}`),
        api(`/api/v1/reports/items?day=${day}`)
    ])
    .then(([summary, items]) => {
        const money = cents => `$${(cents / 100).toFixed(2)}`;
        const itemTable = (title, rows) => `
            <div>
                <h3>${title}</h3>
                <table class="data-table">
                    <thead><tr><th>Item</th><th>Sold</th><th>Sales</th></tr></thead>
                    <tbody>${rows.length === 0 ? '<tr><td colspan="3">None sold</td></tr>' : rows.map(row => `
                        <tr><td>${escapeHtml(row.name)}</td><td>${row.qty}</td><td>${money(row.sales_cents)}</td></tr>`).join('')}</tbody>
                </table>
            </div>`;
        body.innerHTML = `
            <div class="stat-cards">
                <div class="stat-card"><span>Total sales</span><strong>${money(summary.total_sales_cents)}</strong></div>
                <div class="stat-card"><span>Tickets</span><strong>${summary.ticket_count}</strong></div>
                <div class="stat-card"><span>Average ticket</span><strong>${money(summary.average_ticket_cents)}</strong></div>
            </div>
            <div class="item-columns">
                ${itemTable('Food', items.food)}
                ${itemTable('Drinks', items.drinks)}
            </div>`;
    })
    .catch(error => {
        body.innerHTML = `<p class="status-note">Could not load the summary (${escapeHtml(error.message)}).</p>`;
    });
}

function confirmEndOfDay() {
    const day = document.getElementById('sum-date').value;
    const body = openModal('End of day', `
        <p>Export the sales for <strong>${escapeHtml(day)}</strong> to files on the server?</p>
        <button id="eod-confirm" class="btn-large">Export</button>
        <button id="eod-cancel" class="btn-large">Cancel</button>`);
    body.querySelector('#eod-cancel').addEventListener('click', closeModal);
    body.querySelector('#eod-confirm').addEventListener('click', () => {
        closeModal();
        api(`/api/v1/admin/end-of-day?date=${day}`, { method: 'POST' })
            .then(result => {
                const weekly = result.weekly ? ` Weekly report ${result.weekly.start} to ${result.weekly.end} written to ${result.weekly.folder}.` : '';
                document.getElementById('sum-status').textContent =
                    `Exported ${result.date} to ${result.folder}: summary.csv, item_sales.csv, hourly.csv.${weekly}`;
            })
            .catch(error => alert('End of day failed: ' + error.message));
    });
}

// Command Center: current sales, active tickets, and sales / labor / labor % by hour
function loadDayStats() {
    const block = document.getElementById('stats-block');
    if (!block) return;
    api('/api/v1/admin/stats')
        .then(stats => {
            const money = cents => `$${(cents / 100).toFixed(2)}`;
            const pct = value => value === null ? '-' : `${value.toFixed(1)}%`;
            block.innerHTML = `
                <div class="stat-cards">
                    <div class="stat-card"><span>Sales today</span><strong>${money(stats.sales_cents)}</strong></div>
                    <div class="stat-card"><span>Active tickets</span><strong>${stats.active_tickets}</strong></div>
                    <div class="stat-card"><span>Labor today</span><strong>${money(stats.labor_cents)}</strong></div>
                    <div class="stat-card"><span>Labor %</span><strong>${pct(stats.labor_pct)}</strong></div>
                </div>
                <h3>By hour</h3>
                <table class="data-table">
                    <thead><tr><th>Hour</th><th>Sales</th><th>Labor</th><th>Labor %</th></tr></thead>
                    <tbody>${stats.hours.length === 0 ? '<tr><td colspan="4">No activity yet</td></tr>' : stats.hours.map(row => `
                        <tr>
                            <td>${row.hour}</td>
                            <td>${money(row.sales_cents)}</td>
                            <td>${money(row.labor_cents)}</td>
                            <td>${pct(row.labor_pct)}</td>
                        </tr>`).join('')}</tbody>
                </table>`;
        })
        .catch(error => {
            block.innerHTML = `<p class="status-note">Could not load sales (${escapeHtml(error.message)}).</p>`;
        });
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
            const tables = seats.filter(seat => !seat.seat.startsWith('BAR'));
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
                <button id="done-table-btn" class="btn-large">Done</button>
            `);
            body.querySelector('#done-table-btn').addEventListener('click', closeModal);
        })
        .catch(error => alert('Error loading table: ' + error.message));
}

// Server screen implementation
function renderServer(root) {
    api('/api/v1/parties?open=true')
        .then(openParties => {
            root.innerHTML = `
                <div class="card">
                    <h2>My Tables</h2>
                    <div class="grid-buttons" id="server-tables-grid">
                        ${openParties.map(party => `
                            <button class="button-card" data-party-id="${party.id}" data-seat="${party.seat}"
                                    data-name="${escapeHtml(party.party_name)}">
                                ${party.seat}<br>${escapeHtml(party.party_name)}<br>${fmtElapsed(party.opened_at)}
                            </button>`).join('')}
                    </div>
                    ${openParties.length === 0 ? '<p>No tables assigned to you right now.</p>' : ''}
                </div>`;

            // Tap a table: a small pop-up beside it to place an order, the same as the bar
            document.querySelectorAll('#server-tables-grid button').forEach(button => {
                button.addEventListener('click', function() {
                    const seat = { seat: this.dataset.seat, party: { id: parseInt(this.dataset.partyId, 10), party_name: this.dataset.name } };
                    showSeatPopover(this, seat, root, 'server');
                });
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
            // Bar seats only (BAR1-BAR10)
            const barSeats = seats.filter(seat => seat.seat.startsWith('BAR'));
            
            root.innerHTML = `
                <div class="card">
                    <h2>Bar Station</h2>
                    <div class="grid-buttons" id="bar-seats-grid">
                        ${barSeats.map(seat => `
                            <button 
                                class="button-card"
                                data-seat="${seat.seat}" 
                                data-occupied="${!!seat.party}"
                            >
                                ${seat.seat}<br>
                                ${seat.party ? escapeHtml(seat.party.party_name) + '<br>' + fmtElapsed(seat.party.opened_at) : 'Empty'}
                            </button>
                        `).join('')}
                    </div>
                </div>
            `;
            
            // Add event listeners to buttons
            document.querySelectorAll('#bar-seats-grid button').forEach(button => {
                button.addEventListener('click', function() {
                    const seatCode = this.dataset.seat;
                    const seat = barSeats.find(item => item.seat === seatCode);
                    if (seat.party) {
                        // Occupied seat: a small pop-up beside it to place an order
                        showSeatPopover(this, seat, root);
                    } else {
                        // Empty seat: name the party
                        showCreatePartyForm(root, seatCode);
                    }
                });
            });
            
        })
        .catch(error => {
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${error.message}</p></div>`;
            console.error('Error loading bar seats:', error);
        });
}

// Drink queue: one card per party, all of its drinks together, oldest first
function renderDrinkQueue(root) {
    root.innerHTML = `
        <div class="card">
            <h2>Drink Queue</h2>
            <p id="queue-status" class="status-note"></p>
            <div id="drink-queue" class="queue-grid"></div>
        </div>`;
    loadDrinkQueue();
    if (window.KIS.queueInterval) {
        clearInterval(window.KIS.queueInterval);
    }
    window.KIS.queueInterval = setInterval(loadDrinkQueue, 2000);
}

function loadDrinkQueue() {
    const box = document.getElementById('drink-queue');
    if (!box) return;
    // Remember where each ticket was, so the rest can slide over when one is bumped
    const before = {};
    box.querySelectorAll('.queue-card').forEach(card => {
        before[card.dataset.orderId] = card.getBoundingClientRect().left;
    });

    api('/api/v1/tickets?track=bar')
        .then(tickets => {
            document.getElementById('queue-status').textContent = '';
            if (tickets.length === 0) {
                box.innerHTML = '<p>No drinks waiting.</p>';
                return;
            }
            box.innerHTML = tickets.map(ticket => `
                <div class="card ticket-card queue-card" data-order-id="${ticket.order_id}">
                    <p><strong>${escapeHtml(ticket.seat)}</strong> - ${escapeHtml(ticket.party_name)}</p>
                    <p>Waiting: ${fmtElapsed(ticket.opened_at)}</p>
                    ${ticket.items.map(item => `
                        <div class="order-item-card">
                            <p><strong>${escapeHtml(item.name)}</strong> x${item.qty}${item.notes ? ' | ' + escapeHtml(item.notes) : ''}</p>
                            ${item.voided ? '<span class="voided-badge">VOID</span>' : ''}
                        </div>`).join('')}
                    <button class="btn-large drinks-ready-btn" data-order-id="${ticket.order_id}">Drinks ready</button>
                    ${ticket.seat.startsWith('BAR')
                        ? `<button class="btn-large queue-payment-btn" data-party-id="${ticket.party_id}">Send to Payment</button>`
                        : '<p class="ticket-hint">Table: sent to payment by the server</p>'}
                </div>`).join('');

            // Slide each remaining ticket from where it was to its new place
            box.querySelectorAll('.queue-card').forEach(card => {
                const previous = before[card.dataset.orderId];
                if (previous === undefined) return;
                const shift = previous - card.getBoundingClientRect().left;
                if (Math.abs(shift) < 1) return;
                card.style.transition = 'none';
                card.style.transform = `translateX(${shift}px)`;
                requestAnimationFrame(() => requestAnimationFrame(() => {
                    card.style.transition = 'transform 0.45s ease';
                    card.style.transform = '';
                }));
            });

            box.querySelectorAll('.drinks-ready-btn').forEach(button => {
                button.addEventListener('click', () => {
                    api(`/api/v1/tickets/${button.dataset.orderId}/bar/bump`, { method: 'POST' })
                        .then(loadDrinkQueue)
                        .catch(error => alert('Could not mark drinks ready: ' + error.message));
                });
            });
            box.querySelectorAll('.queue-payment-btn').forEach(button => {
                button.addEventListener('click', () => {
                    api(`/api/v1/parties/${button.dataset.partyId}/close`, { method: 'POST' })
                        .then(loadDrinkQueue)
                        .catch(error => alert('Could not send to payment: ' + error.message));
                });
            });
        })
        .catch(error => {
            document.getElementById('queue-status').textContent = `Could not load the queue (${error.message}). Retrying...`;
        });
}

// Server notice: drinks for one of the server's tables are ready. Dismissed per ready time.
function checkDrinkAlerts() {
    if (!state.employee || state.employee.role !== 'server') {
        const banner = document.getElementById('drink-alerts');
        if (banner) banner.innerHTML = '';
        return;
    }
    api('/api/v1/parties?open=true')
        .then(parties => {
            const banner = document.getElementById('drink-alerts');
            if (!banner) return;
            const dismissed = JSON.parse(sessionStorage.getItem('kisnet.dismissedDrinks') || '{}');
            const ready = parties.filter(party => party.drinks_ready_at && dismissed[party.id] !== party.drinks_ready_at);
            banner.innerHTML = ready.map(party => `
                <div class="drink-alert">
                    <strong>Drinks ready:</strong> ${escapeHtml(party.seat)} - ${escapeHtml(party.party_name)}
                    <button class="btn-large dismiss-drink-alert" data-party="${party.id}" data-ready="${escapeHtml(party.drinks_ready_at)}">Dismiss</button>
                </div>`).join('');
            banner.querySelectorAll('.dismiss-drink-alert').forEach(button => {
                button.addEventListener('click', () => {
                    const seen = JSON.parse(sessionStorage.getItem('kisnet.dismissedDrinks') || '{}');
                    seen[button.dataset.party] = button.dataset.ready;
                    sessionStorage.setItem('kisnet.dismissedDrinks', JSON.stringify(seen));
                    checkDrinkAlerts();
                });
            });
        })
        .catch(() => {});
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
    const categories = ['cold', 'appetizers', 'hot'];
    
    root.innerHTML = `
        <div class="card">
            <h2>Kitchen Station</h2>
            <div class="grid-buttons" id="kitchen-columns">
                ${categories.map(category => `
                    <div class="kitchen-column">
                        <h3>${category === 'appetizers' ? 'Apps' : category.charAt(0).toUpperCase() + category.slice(1)}</h3>
                        <div id="${category}-tickets" class="ticket-stack"></div>
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
    '/bar': renderDrinkQueue,
    '/barseats': renderBar,
    '/kitchen': renderKitchen,
    '/timecard': renderTimeCard,
    '/summary': renderSummary,
    '/employees': renderEmployees,
    '/recipes': renderRecipes,
    '/home': renderHome
};

// Home: default landing page; clock in from Login
function renderHome(root) {
    root.innerHTML = `
        <div class="card">
            <h2>KISnet POS</h2>
            <p>Welcome. Use <strong>Clock In</strong> on the login page to start your shift, then <strong>Log In</strong> to open your station. Clock Out is on the <strong>Time Card</strong>.</p>
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
    wrap.querySelector('#tc-clock-out').addEventListener('click', () => confirmClockOut(card));
    return wrap;
}

// Logout: end this session but stay on the clock (clocking out lives on the Time Card)
function logout() {
    api('/auth/logout', { method: 'POST' })
        .catch(() => {})
        .then(() => {
            sessionStorage.removeItem('kisnet.token');
            sessionStorage.removeItem('kisnet.returnTo');
            state.employee = null;
            state.token = null;
            renderMenu();
            go('#/login');
        });
}

// Clock out asks first: it ends the shift, and the person must clock in again to start another
function confirmClockOut(card) {
    const body = openModal('Confirm clock out', `
        <p><strong>Name:</strong> ${escapeHtml(card.employee.name)}</p>
        <p><strong>Time:</strong> ${fmtDate(new Date().toISOString())}</p>
        <p>This ends your shift. Clock out now?</p>
        <button id="confirm-clock-out-btn" class="btn-large">Confirm clock out</button>
        <button id="cancel-clock-out-btn" class="btn-large">Cancel</button>
    `);
    body.querySelector('#cancel-clock-out-btn').addEventListener('click', closeModal);
    body.querySelector('#confirm-clock-out-btn').addEventListener('click', () => {
        closeModal();
        clockOut();
    });
}

// Clock out function
function clockOut() {
    sessionStorage.removeItem('kisnet.returnTo');
    api('/auth/clock-out', { method: 'POST' })
        .then(() => {
            // Clear local storage and state
            sessionStorage.removeItem('kisnet.token');
            state.employee = null;
            state.token = null;
            renderMenu();
            
            // Go back to login
            go('#/login');
        })
        .catch(error => {
            console.error('Clock out error:', error);
            // Still redirect to login even if clock-out failed
            sessionStorage.removeItem('kisnet.token');
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
        const canToggle = state.employee.role === 'bartender' || state.employee.role === 'admin';
        const onSeats = window.location.hash.slice(1) === '/barseats';
        topBar.innerHTML = `
            <div>Welcome, ${state.employee.name} (${state.employee.role})</div>
            <div class="top-actions">
                ${canToggle ? `<button id="view-toggle" class="btn-large">${onSeats ? 'Drink Queue' : 'Bar Seats'}</button>` : ''}
                <button id="logout-btn" class="btn-large">Logout</button>
            </div>
        `;
        
        document.getElementById('app').prepend(topBar);
        
        // Add event listener for clock out button
        document.getElementById('logout-btn').addEventListener('click', logout);
        const toggle = document.getElementById('view-toggle');
        if (toggle) {
            toggle.addEventListener('click', () => go(window.location.hash.slice(1) === '/barseats' ? '/bar' : '/barseats'));
        }
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
    '/bar': 'Drink Queue', '/barseats': 'Bar Seats', '/kitchen': 'Kitchen', '/timecard': 'Time Card',
    '/summary': 'Daily Summary', '/employees': 'Employees', '/recipes': 'Recipes'
};

// The three-bar menu sits outside the screens, so it is available on every page
function buildMenuChrome() {
    document.body.insertAdjacentHTML('beforeend', `
        <div id="drink-alerts" class="drink-alerts"></div>
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
        paths = ['/command', '/summary', '/reports', '/host', '/server', '/barseats', '/bar', '/kitchen', '/timecard',
                 '/employees', '/recipes'];
    } else {
        paths = state.employee.role === 'bartender'
            ? ['/barseats', '/bar', '/timecard']
            : [stationFor(state.employee.role), '/timecard'];
    }
    menu.innerHTML = '<h3 class="side-menu-title">Menu</h3>';
    paths.forEach((path, index) => {
        // Admin's System section (Employees and Recipes) sits under its own heading
        if (path === '/employees') {
            menu.insertAdjacentHTML('beforeend', '<h3 class="side-menu-title side-menu-section">System</h3>');
        }
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
        const token = sessionStorage.getItem('kisnet.token');
        if (token) {
            api('/auth/me')
                .then(data => {
                    state.employee = data;
                    state.token = token;
                    const current = window.location.hash.slice(1);
                    goTo(current && canVisit(data.role, current) ? current : stationFor(data.role));
                })
                .catch(() => {
                    sessionStorage.removeItem('kisnet.token');
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
    // Session is kept per browser tab (sessionStorage), so each tab can run its own screen
    buildMenuChrome();
    setInterval(checkDrinkAlerts, 3000);

    // Listen for hash changes
    window.addEventListener('hashchange', updateScreen);

    // Any input counts as activity; check for idleness every 15 seconds
    ['pointerdown', 'keydown', 'mousemove', 'touchstart', 'input', 'scroll'].forEach(type =>
        document.addEventListener(type, () => { lastActivity = Date.now(); }, { passive: true }));
    setInterval(() => {
        if (sessionStorage.getItem('kisnet.token') && Date.now() - lastActivity > IDLE_LIMIT_MS) {
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
    if (window.KIS && window.KIS.queueInterval) {
        clearInterval(window.KIS.queueInterval);
        window.KIS.queueInterval = null;
    }
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
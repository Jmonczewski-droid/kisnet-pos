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
                return response.json().catch(() => ({})).then(err => {
                    const error = new Error(typeof err.detail === 'string' ? err.detail : `HTTP error! status: ${response.status}`);
                    error.status = response.status;
                    error.code = response.headers.get('X-Error-Code');  // e.g. pin_change_required, otp_required
                    throw error;
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

// Database management screens: the owner only
const OWNER_PATHS = ['/employees', '/recipes', '/devices'];

function isOwner() {
    return !!state.employee && state.employee.access === 'owner';
}

function canVisit(role, path) {
    if (OWNER_PATHS.includes(path)) return role === 'admin' && isOwner();
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
                    <p><strong>Seat:</strong> ${escapeHtml(party.seat)}</p>
                    <p><strong>Party Name:</strong> ${escapeHtml(party.party_name)}</p>
                    <p><strong>Party Size:</strong> ${party.party_size}</p>
                    <p><strong>Server:</strong> ${escapeHtml(party.server_name || 'None')}</p>
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
                                        <p><strong>${escapeHtml(item.name)}</strong> - Qty: ${item.qty} 
                                            ${item.notes ? ` | Notes: ${escapeHtml(item.notes)}` : ''}
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
                                <h4>${escapeHtml(category.charAt(0).toUpperCase() + category.slice(1))}</h4>
                                <div class="grid-buttons">
                                    ${items.map(item => `
                                        <button 
                                            class="menu-item-btn"
                                            data-item-id="${item.id}"
                                            data-category="${escapeHtml(item.category)}"
                                            data-name="${escapeHtml(item.name)}"
                                            data-price="${item.price_cents}"
                                        >
                                            ${escapeHtml(item.name)}<br>
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
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${escapeHtml(error.message)}</p></div>`;
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

    startClockIn(credentials);
}

function startClockIn(credentials) {
    api('/auth/preview', { method: 'POST', body: JSON.stringify(credentials) })
        .then(preview => {
            if (preview.on_clock) {
                setLoginMessage(`${preview.employee.name} is already clocked in.`);
                return;
            }
            confirmClockIn(preview, credentials);
        })
        .catch(error => {
            if (error.code === 'pin_change_required') { promptOwnPin(credentials, startClockIn); return; }
            setLoginMessage(error.message);
        });
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
                   ${positions.map(role => `<option value="${escapeHtml(role)}">${escapeHtml(roleLabel(role))}</option>`).join('')}
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

    startLogIn(credentials);
}

function startLogIn(credentials) {
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
        .catch(error => {
            const { otp, ...withoutCode } = credentials;
            if (error.code === 'pin_change_required') { promptOwnPin(withoutCode, startLogIn); return; }
            if (error.code === 'otp_required' || error.code === 'otp_invalid') {
                promptAuthenticatorCode(error.code === 'otp_invalid' ? error.message : '',
                                        code => startLogIn({ ...withoutCode, otp: code }));
                return;
            }
            setLoginMessage(error.message);
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

// System > Employees and Recipes (admin): edit, deactivate, reactivate and archive
const POSITION_OPTIONS = ['host', 'server', 'bartender', 'kitchen'];  // stations; access level decides management rights
const ACCESS_LABELS = { owner: 'Owner', manager: 'Manager', team: 'Team Member' };
const ACCESS_HELP = {
    owner: 'Full access, including this employee database, recipes and devices.',
    manager: 'Runs the restaurant: command center, reports, end of day and every station. No database management.',
    team: 'Works the stations ticked below.'
};
const ACTION_DONE = { deactivate: 'Deactivated', reactivate: 'Reactivated', archive: 'Archived' };
let rosterRows = [];
let recipeRows = [];
let editingRecipeId = null;

// Buttons for one roster or recipe row. Archived rows are read only.
function rowActions(status, id) {
    if (status === 'archived') return '<em>Archived</em>';
    const edit = `<button class="btn-large" data-action="edit" data-id="${id}">Edit</button>`;
    const toggle = status === 'active'
        ? `<button class="btn-large" data-action="deactivate" data-id="${id}">Deactivate</button>`
        : `<button class="btn-large" data-action="reactivate" data-id="${id}">Reactivate</button>`;
    const archive = `<button class="btn-large" data-action="archive" data-id="${id}">Archive</button>`;
    return edit + toggle + archive;
}

function statusLabel(status) {
    return status.charAt(0).toUpperCase() + status.slice(1);
}

function renderEmployees(root) {
    root.innerHTML = `
        <div class="card">
            <h2>Employees</h2>
            <div class="week-nav">
                <button id="emp-add-toggle" class="btn-large">Add employee</button>
                <label class="checkbox-row"><input type="checkbox" id="emp-show-archived"> Show archived</label>
            </div>
            <div id="emp-form"></div>
            <p id="emp-status" class="status-note"></p>
            <div id="emp-roster"></div>
        </div>`;
    document.getElementById('emp-add-toggle').addEventListener('click', () => showEmployeeForm(null));
    document.getElementById('emp-show-archived').addEventListener('change', loadRoster);
    document.getElementById('emp-roster').addEventListener('click', handleRosterClick);
    loadRoster();
}

function loadRoster() {
    const box = document.getElementById('emp-roster');
    if (!box) return;
    const archived = document.getElementById('emp-show-archived').checked;
    api(`/api/v1/admin/roster?include_archived=${archived}`)
        .then(rows => {
            rosterRows = rows;
            const money = hours => `${hours.toFixed(2)} h`;
            box.innerHTML = `
                <table class="data-table">
                    <thead><tr><th>Code</th><th>Name</th><th>Access</th><th>Positions</th><th>Sign-in</th><th>Status</th><th>Hire date</th><th>SSN</th>
                        <th>On clock</th><th>Hours this week</th><th>Address</th><th>DOB</th><th></th></tr></thead>
                    <tbody>${rows.map(row => `
                        <tr style="${row.status === 'archived' ? 'opacity: 0.6' : ''}">
                            <td>${escapeHtml(row.code)}</td>
                            <td>${escapeHtml(row.name)}</td>
                            <td>${escapeHtml(ACCESS_LABELS[row.access] || row.access)}</td>
                            <td>${row.positions.filter(role => role !== 'admin').map(role => escapeHtml(roleLabel(role))).join(', ')}</td>
                            <td>${[row.locked ? 'Locked' : '', row.pin_is_temporary ? 'Starter PIN' : 'Own PIN', row.two_step ? 'Two-step' : ''].filter(Boolean).join(', ')}</td>
                            <td>${statusLabel(row.status)}</td>
                            <td>${row.hire_date || ''}</td>
                            <td>${escapeHtml(row.ssn)}</td>
                            <td>${row.on_clock ? 'Yes' : ''}</td>
                            <td>${money(row.week_hours)}</td>
                            <td>${escapeHtml(row.address || '')}</td>
                            <td>${row.dob || ''}</td>
                            <td>${rowActions(row.status, row.id)}</td>
                        </tr>`).join('')}</tbody>
                </table>`;
        })
        .catch(error => {
            box.innerHTML = `<p class="status-note">Could not load the roster (${escapeHtml(error.message)}).</p>`;
        });
}

function handleRosterClick(event) {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const id = Number(button.dataset.id);
    const row = rosterRows.find(item => item.id === id);
    const action = button.dataset.action;
    if (action === 'edit') { showEmployeeForm(row); return; }
    if (action === 'archive' && !window.confirm(`Archive ${row.name}? They will be removed from the roster and cannot log in. The record is kept.`)) return;
    const status = document.getElementById('emp-status');
    const form = document.getElementById('emp-form');
    api(`/api/v1/admin/employees/${id}/${action}`, { method: 'POST' })
        .then(() => {
            if (form.dataset.editing === String(id)) form.innerHTML = '';
            status.textContent = `${ACTION_DONE[action]} ${row.name}.`;
            loadRoster();
        })
        .catch(error => { status.textContent = `Could not ${action} ${row.name}: ${error.message}`; });
}

// Add form when employee is null; otherwise the same form prefilled for editing (PIN blank keeps the current one)
function showEmployeeForm(employee) {
    const editing = employee !== null;
    const form = document.getElementById('emp-form');
    form.dataset.editing = editing ? String(employee.id) : '';
    const held = editing ? employee.positions : [];
    form.innerHTML = `
        <div class="form-group"><label for="emp-name">Name</label><input type="text" id="emp-name" value="${editing ? escapeHtml(employee.name) : ''}"></div>
        <div class="form-group"><label for="emp-address">Address</label><input type="text" id="emp-address" value="${editing ? escapeHtml(employee.address || '') : ''}"></div>
        <div class="form-group"><label for="emp-dob">Date of birth</label><input type="date" id="emp-dob" value="${editing && employee.dob ? employee.dob : ''}"></div>
        <div class="form-group"><label for="emp-hire">Hire date</label><input type="date" id="emp-hire" value="${editing ? (employee.hire_date || '') : isoDay(new Date())}"></div>
        <div class="form-group"><label for="emp-access">Access level</label>
            <select id="emp-access">
                ${Object.keys(ACCESS_LABELS).reverse().map(level => `<option value="${level}"${(editing ? employee.access : 'team') === level ? ' selected' : ''}>${ACCESS_LABELS[level]}</option>`).join('')}
            </select>
            <small id="emp-access-help"></small></div>
        <fieldset class="form-group">
            <legend>Stations (tick every job this person can work)</legend>
            ${POSITION_OPTIONS.map(role => `
                <label class="checkbox-row"><input type="checkbox" class="emp-position" value="${escapeHtml(role)}"${held.includes(role) ? ' checked' : ''}> ${escapeHtml(roleLabel(role))}</label>`).join('')}
        </fieldset>
        <div class="form-group"><label for="emp-pin">${editing ? 'New starter PIN (leave blank to keep their PIN)' : 'Starter PIN (4 or more characters)'}</label>
            <input type="text" id="emp-pin" autocomplete="off" value="${editing ? '' : '1234'}">
            <small>Give this to the employee. They must replace it with their own PIN the first time they sign in, so nobody else knows it.${editing ? ' Setting one also unlocks a locked sign-in.' : ''}</small></div>
        <button id="emp-save" class="btn-large">${editing ? 'Save changes' : 'Save employee'}</button>
        <button id="emp-cancel" class="btn-large">Cancel</button>`;
    const access = document.getElementById('emp-access');
    const showAccessHelp = () => { document.getElementById('emp-access-help').textContent = ACCESS_HELP[access.value]; };
    access.addEventListener('change', showAccessHelp);
    showAccessHelp();
    document.getElementById('emp-cancel').addEventListener('click', () => { form.innerHTML = ''; });
    document.getElementById('emp-save').addEventListener('click', () => saveEmployee(editing ? employee.id : null));
    document.getElementById('emp-name').focus();
}

function saveEmployee(id) {
    const positions = [...document.querySelectorAll('.emp-position:checked')].map(box => box.value);
    const name = document.getElementById('emp-name').value.trim();
    if (!name) { alert('Enter the name'); return; }
    const access = document.getElementById('emp-access').value;
    if (positions.length === 0 && access === 'team') { alert('Tick at least one station for a team member'); return; }
    const pin = document.getElementById('emp-pin').value;
    const body = {
        name,
        address: document.getElementById('emp-address').value.trim() || null,
        dob: document.getElementById('emp-dob').value || null,
        hire_date: document.getElementById('emp-hire').value || null,
        positions,
        access
    };
    if (pin || id === null) body.pin = pin;
    const request = id === null
        ? api('/api/v1/admin/employees', { method: 'POST', body: JSON.stringify(body) })
        : api(`/api/v1/admin/employees/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    request
        .then(saved => {
            document.getElementById('emp-form').innerHTML = '';
            document.getElementById('emp-status').textContent = `${id === null ? 'Added' : 'Saved'} ${saved.code} ${saved.name}.`;
            loadRoster();
        })
        .catch(error => alert(`Could not save the employee: ${error.message}`));
}

function renderRecipes(root) {
    editingRecipeId = null;
    root.innerHTML = `
        <div class="card">
            <h2>Recipes</h2>
            <h3 id="rec-form-title">Add a recipe</h3>
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
            <button id="rec-cancel" class="btn-large" hidden>Cancel edit</button>
            <p id="rec-status" class="status-note"></p>
            <h3>Recipes on the menu</h3>
            <label class="checkbox-row"><input type="checkbox" id="rec-show-archived"> Show archived</label>
            <div id="rec-list"></div>
        </div>`;
    addIngredientRow();
    document.getElementById('rec-add-ingredient').addEventListener('click', () => addIngredientRow());
    document.getElementById('rec-save').addEventListener('click', saveRecipe);
    document.getElementById('rec-cancel').addEventListener('click', resetRecipeForm);
    document.getElementById('rec-show-archived').addEventListener('change', loadRecipeList);
    document.getElementById('rec-list').addEventListener('click', handleRecipeClick);
    loadRecipeList();
}

function addIngredientRow(line = { ingredient: '', qty: '', unit: '' }) {
    const box = document.getElementById('rec-ingredients');
    const row = document.createElement('div');
    row.className = 'ingredient-row';
    row.innerHTML = `
        <input type="text" class="ing-name" placeholder="Ingredient" value="${escapeHtml(line.ingredient)}">
        <input type="number" class="ing-qty" min="0" step="0.1" placeholder="Qty" value="${line.qty}">
        <input type="text" class="ing-unit" placeholder="Unit (oz, each)" value="${escapeHtml(line.unit)}">`;
    box.appendChild(row);
}

// Back to the empty add form (after saving, or cancelling an edit)
function resetRecipeForm() {
    editingRecipeId = null;
    document.getElementById('rec-form-title').textContent = 'Add a recipe';
    document.getElementById('rec-save').textContent = 'Save recipe';
    document.getElementById('rec-cancel').hidden = true;
    document.getElementById('rec-name').value = '';
    document.getElementById('rec-category').value = 'bar';
    document.getElementById('rec-price').value = '';
    document.getElementById('rec-ingredients').innerHTML = '';
    addIngredientRow();
}

function startRecipeEdit(recipe) {
    resetRecipeForm();
    editingRecipeId = recipe.id;
    document.getElementById('rec-form-title').textContent = `Edit ${recipe.name}`;
    document.getElementById('rec-save').textContent = 'Save changes';
    document.getElementById('rec-cancel').hidden = false;
    document.getElementById('rec-name').value = recipe.name;
    document.getElementById('rec-category').value = recipe.category;
    document.getElementById('rec-price').value = (recipe.price_cents / 100).toFixed(2);
    document.getElementById('rec-ingredients').innerHTML = '';
    recipe.ingredients.forEach(line => addIngredientRow(line));
    if (recipe.ingredients.length === 0) addIngredientRow();
    document.getElementById('rec-name').focus();
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
    const id = editingRecipeId;
    const body = JSON.stringify({ name, category: document.getElementById('rec-category').value,
                                  price_cents: Math.round(price * 100), ingredients });
    const request = id === null
        ? api('/api/v1/admin/recipes', { method: 'POST', body })
        : api(`/api/v1/admin/recipes/${id}`, { method: 'PUT', body });
    request
        .then(saved => {
            status.textContent = `${id === null ? 'Added' : 'Saved'} ${saved.name} at $${(saved.price_cents / 100).toFixed(2)}.`;
            resetRecipeForm();
            loadRecipeList();
        })
        .catch(error => { status.textContent = `Could not save: ${error.message}`; });
}

function loadRecipeList() {
    const box = document.getElementById('rec-list');
    if (!box) return;
    const archived = document.getElementById('rec-show-archived').checked;
    api(`/api/v1/admin/recipes?include_archived=${archived}`)
        .then(recipes => {
            recipeRows = recipes;
            box.innerHTML = `
                <table class="data-table">
                    <thead><tr><th>Name</th><th>Category</th><th>Price</th><th>Ingredients</th><th>Status</th><th></th></tr></thead>
                    <tbody>${recipes.map(recipe => `
                        <tr style="${recipe.status === 'archived' ? 'opacity: 0.6' : ''}">
                            <td>${escapeHtml(recipe.name)}</td>
                            <td>${escapeHtml(roleLabel(recipe.category))}</td>
                            <td>$${(recipe.price_cents / 100).toFixed(2)}</td>
                            <td>${recipe.ingredients.map(line => `${line.qty} ${escapeHtml(line.unit)} ${escapeHtml(line.ingredient)}`).join(', ')}</td>
                            <td>${statusLabel(recipe.status)}</td>
                            <td>${rowActions(recipe.status, recipe.id)}</td>
                        </tr>`).join('')}</tbody>
                </table>`;
        })
        .catch(error => {
            box.innerHTML = `<p class="status-note">Could not load recipes (${escapeHtml(error.message)}).</p>`;
        });
}

function handleRecipeClick(event) {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const id = Number(button.dataset.id);
    const recipe = recipeRows.find(item => item.id === id);
    const action = button.dataset.action;
    if (action === 'edit') { startRecipeEdit(recipe); return; }
    if (action === 'archive' && !window.confirm(`Archive ${recipe.name}? It will be removed from the menu for good. Past sales are kept.`)) return;
    const status = document.getElementById('rec-status');
    api(`/api/v1/admin/recipes/${id}/${action}`, { method: 'POST' })
        .then(() => {
            if (editingRecipeId === id) resetRecipeForm();
            status.textContent = `${ACTION_DONE[action]} ${recipe.name}.`;
            loadRecipeList();
        })
        .catch(error => { status.textContent = `Could not ${action} ${recipe.name}: ${error.message}`; });
}

// ---------------------------------------------------------------------------------------------
// Device management (admin): printers and monitors, and the portal that connects them
// ---------------------------------------------------------------------------------------------
const JOB_LABELS = { bar: 'Bar', appetizers: 'Apps', hot: 'Hot', cold: 'Cold', receipt: 'Guest receipts' };
const CONNECTION_LABELS = {
    ok: 'Working', error: 'Not responding', untested: 'Not tested yet',
    online: 'Online', offline: 'Offline', waiting: 'Waiting for device', 'not paired': 'Not connected'
};
let deviceRows = [];
let editingDeviceId = null;

let serverAddress = null;  // this server's address on the local network, once known

// The address other devices should open. If the manager is on the server itself ("localhost"),
// swap in the server's network address, because localhost means something else on a phone or tablet.
function networkOrigin() {
    const local = ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname);
    if (local && serverAddress && serverAddress.addresses.length > 0) {
        return `${serverAddress.scheme}://${serverAddress.addresses[0]}:${serverAddress.port}`;
    }
    return window.location.origin;
}

function displayUrl() {
    return `${networkOrigin()}/#/display`;
}

function loadServerAddress() {
    api('/api/v1/admin/server-address')
        .then(info => {
            serverAddress = info;
            const box = document.getElementById('dev-address');
            if (box) box.textContent = networkOrigin();
            loadDeviceList();
        })
        .catch(() => {});
}

function renderDevices(root) {
    editingDeviceId = null;
    root.innerHTML = `
        <div class="card">
            <h2>Device Management</h2>
            <p>Connect the printers and screens this restaurant uses. Works with PCs, Android and Apple devices, including phones.</p>
            <p>Phones, tablets and screens on the same network open the POS at <strong id="dev-address"></strong></p>
            <h3 id="dev-form-title">Add a device</h3>
            <div class="form-group"><label for="dev-name">Name</label><input type="text" id="dev-name" maxlength="60" placeholder="Kitchen printer, Bar screen..."></div>
            <div class="form-group">
                <label for="dev-kind">Type</label>
                <select id="dev-kind">
                    <option value="printer">Printer</option>
                    <option value="monitor">Monitor (ticket screen)</option>
                </select>
            </div>
            <div class="form-group">
                <label id="dev-jobs-label">What it prints</label>
                ${Object.keys(JOB_LABELS).map(job => `
                    <label class="checkbox-row" data-job="${job}"><input type="checkbox" class="dev-job" value="${job}"> ${JOB_LABELS[job]}</label>`).join('')}
            </div>
            <div id="dev-printer-fields">
                <div class="form-group"><label for="dev-host">Printer network address (IP)</label><input type="text" id="dev-host" placeholder="192.168.1.50"></div>
                <div class="form-group"><label for="dev-port">Port</label><input type="number" id="dev-port" min="1" max="65535" value="9100"></div>
            </div>
            <button id="dev-save" class="btn-large">Add device</button>
            <button id="dev-cancel" class="btn-large" hidden>Cancel edit</button>
            <p id="dev-status" class="status-note"></p>
            <h3>Connected devices</h3>
            <label class="checkbox-row"><input type="checkbox" id="dev-show-archived"> Show archived</label>
            <div id="dev-list"></div>
            <h3>Guest receipt</h3>
            <p>The receipt layout is the file <code>app/templates/receipt.txt</code> on the server. This is how it prints now:</p>
            <pre id="dev-receipt" class="receipt-preview"></pre>
        </div>`;
    document.getElementById('dev-kind').addEventListener('change', syncDeviceForm);
    document.getElementById('dev-save').addEventListener('click', saveDevice);
    document.getElementById('dev-cancel').addEventListener('click', resetDeviceForm);
    document.getElementById('dev-show-archived').addEventListener('change', loadDeviceList);
    document.getElementById('dev-list').addEventListener('click', handleDeviceClick);
    syncDeviceForm();
    document.getElementById('dev-address').textContent = networkOrigin();
    loadDeviceList();
    loadReceiptPreview();
    loadServerAddress();
    // Keep connection status current while the screen is open
    window.KIS.devicesInterval = setInterval(loadDeviceList, 5000);
}

// Printers have an address and can print receipts; monitors have neither
function syncDeviceForm() {
    const isPrinter = document.getElementById('dev-kind').value === 'printer';
    document.getElementById('dev-printer-fields').hidden = !isPrinter;
    document.getElementById('dev-jobs-label').textContent = isPrinter ? 'What it prints' : 'What it shows';
    const receipt = document.querySelector('.checkbox-row[data-job="receipt"]');
    receipt.hidden = !isPrinter;
    if (!isPrinter) receipt.querySelector('input').checked = false;
}

function resetDeviceForm() {
    editingDeviceId = null;
    document.getElementById('dev-form-title').textContent = 'Add a device';
    document.getElementById('dev-save').textContent = 'Add device';
    document.getElementById('dev-cancel').hidden = true;
    document.getElementById('dev-name').value = '';
    document.getElementById('dev-kind').disabled = false;
    document.getElementById('dev-host').value = '';
    document.getElementById('dev-port').value = '9100';
    document.querySelectorAll('.dev-job').forEach(box => { box.checked = false; });
    syncDeviceForm();
}

function startDeviceEdit(device) {
    resetDeviceForm();
    editingDeviceId = device.id;
    document.getElementById('dev-form-title').textContent = `Edit ${device.name}`;
    document.getElementById('dev-save').textContent = 'Save changes';
    document.getElementById('dev-cancel').hidden = false;
    document.getElementById('dev-name').value = device.name;
    document.getElementById('dev-kind').value = device.kind;
    document.getElementById('dev-kind').disabled = true;  // a printer cannot become a monitor
    document.getElementById('dev-host').value = device.host || '';
    document.getElementById('dev-port').value = device.port || 9100;
    syncDeviceForm();
    document.querySelectorAll('.dev-job').forEach(box => { box.checked = device.jobs.includes(box.value); });
    document.getElementById('dev-name').focus();
}

function saveDevice() {
    const status = document.getElementById('dev-status');
    const name = document.getElementById('dev-name').value.trim();
    const kind = document.getElementById('dev-kind').value;
    const jobs = [...document.querySelectorAll('.dev-job:checked')].map(box => box.value);
    const host = document.getElementById('dev-host').value.trim();
    const port = parseInt(document.getElementById('dev-port').value, 10);
    if (!name) { status.textContent = 'Give the device a name.'; return; }
    if (jobs.length === 0) { status.textContent = `Choose what this ${kind} ${kind === 'printer' ? 'prints' : 'shows'}.`; return; }
    if (kind === 'printer' && !host) { status.textContent = 'Enter the printer\'s network address.'; return; }
    const body = { name, jobs };
    if (kind === 'printer') { body.host = host; body.port = port || 9100; }
    const id = editingDeviceId;
    if (id === null) body.kind = kind;
    const request = id === null
        ? api('/api/v1/admin/devices', { method: 'POST', body: JSON.stringify(body) })
        : api(`/api/v1/admin/devices/${id}`, { method: 'PATCH', body: JSON.stringify(body) });
    request
        .then(saved => {
            status.textContent = id !== null ? `Saved ${saved.name}.`
                : saved.kind === 'monitor' ? `Added ${saved.name}. Enter its code on the screen to connect it.`
                : `Added ${saved.name}. Press Test print to check it.`;
            resetDeviceForm();
            loadDeviceList();
        })
        .catch(error => { status.textContent = `Could not save: ${error.message}`; });
}

function deviceDetail(device) {
    if (device.kind === 'printer') {
        const where = `${escapeHtml(device.host)}:${device.port}`;
        return device.last_error ? `${where}<br><span class="status-note">${escapeHtml(device.last_error)}</span>` : where;
    }
    if (device.pairing_code) {
        return `On the device, open <strong>${escapeHtml(displayUrl())}</strong> and enter
                <span class="pairing-code">${escapeHtml(device.pairing_code)}</span>
                <small>Code expires ${fmtDate(device.pairing_expires_at)}</small>`;
    }
    if (device.connection === 'not paired') return 'Press New code to connect a screen.';
    return `${escapeHtml(device.platform || 'Device')}, last seen ${fmtDate(device.last_seen_at)}`;
}

function deviceActions(device) {
    if (device.status === 'archived') return '<em>Archived</em>';
    const button = (action, label) => `<button class="btn-large" data-action="${action}" data-id="${device.id}">${label}</button>`;
    let extra = '';
    if (device.kind === 'printer') {
        extra = button('test', 'Test print');
    } else {
        extra = button('pairing-code', 'New code');
        if (device.connection === 'online' || device.connection === 'offline') extra += button('unpair', 'Disconnect');
    }
    return extra + rowActions(device.status, device.id);
}

function loadDeviceList() {
    const box = document.getElementById('dev-list');
    if (!box) return;
    const archived = document.getElementById('dev-show-archived').checked;
    api(`/api/v1/admin/devices?include_archived=${archived}`)
        .then(devices => {
            deviceRows = devices;
            if (devices.length === 0) {
                box.innerHTML = '<p>No devices yet. Add a printer or a monitor above.</p>';
                return;
            }
            box.innerHTML = `
                <table class="data-table">
                    <thead><tr><th>Name</th><th>Type</th><th>Prints / shows</th><th>Connection</th><th>Details</th><th>Status</th><th></th></tr></thead>
                    <tbody>${devices.map(device => `
                        <tr style="${device.status === 'archived' ? 'opacity: 0.6' : ''}">
                            <td>${escapeHtml(device.name)}</td>
                            <td>${device.kind === 'printer' ? 'Printer' : 'Monitor'}</td>
                            <td>${device.jobs.map(job => escapeHtml(JOB_LABELS[job] || job)).join(', ')}</td>
                            <td><span class="connection connection-${escapeHtml(device.connection.replace(' ', '-'))}">${escapeHtml(CONNECTION_LABELS[device.connection] || device.connection)}</span></td>
                            <td>${deviceDetail(device)}</td>
                            <td>${escapeHtml(statusLabel(device.status))}</td>
                            <td>${deviceActions(device)}</td>
                        </tr>`).join('')}</tbody>
                </table>`;
        })
        .catch(error => {
            box.innerHTML = `<p class="status-note">Could not load devices (${escapeHtml(error.message)}).</p>`;
        });
}

function loadReceiptPreview() {
    const box = document.getElementById('dev-receipt');
    const token = sessionStorage.getItem('kisnet.token');
    fetch('/api/v1/admin/receipt-preview', { headers: { Authorization: `Bearer ${token}` } })
        .then(response => response.ok ? response.text() : Promise.reject(new Error('preview unavailable')))
        .then(text => { if (box) box.textContent = text; })
        .catch(error => { if (box) box.textContent = `Could not load the receipt (${error.message}).`; });
}

function handleDeviceClick(event) {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const id = Number(button.dataset.id);
    const device = deviceRows.find(item => item.id === id);
    const action = button.dataset.action;
    const status = document.getElementById('dev-status');
    if (action === 'edit') { startDeviceEdit(device); return; }
    if (action === 'archive' && !window.confirm(`Archive ${device.name}? It will be disconnected for good.`)) return;
    if (action === 'pairing-code' && device.connection !== 'not paired' && device.connection !== 'waiting'
        && !window.confirm(`${device.name} is connected. A new code disconnects that screen. Continue?`)) return;
    const done = { test: 'Test page sent to', 'pairing-code': 'New code ready for', unpair: 'Disconnected', ...ACTION_DONE };
    status.textContent = action === 'test' ? `Printing a test page on ${device.name}...` : '';
    api(`/api/v1/admin/devices/${id}/${action}`, { method: 'POST' })
        .then(() => {
            if (editingDeviceId === id) resetDeviceForm();
            status.textContent = `${done[action]} ${device.name}.`;
            loadDeviceList();
        })
        .catch(error => {
            status.textContent = `${device.name}: ${error.message}`;
            loadDeviceList();
        });
}

// ---------------------------------------------------------------------------------------------
// Monitor display: any browser becomes a ticket screen once it is connected with a code.
// The device keeps its own token (not an employee login), so it stays up all day with nobody signed in.
// ---------------------------------------------------------------------------------------------
const DEVICE_TOKEN_KEY = 'kisnet.deviceToken';

function deviceToken() {
    try { return localStorage.getItem(DEVICE_TOKEN_KEY); } catch (error) { return null; }
}

function setDeviceToken(token) {
    try {
        if (token) localStorage.setItem(DEVICE_TOKEN_KEY, token); else localStorage.removeItem(DEVICE_TOKEN_KEY);
    } catch (error) { /* storage blocked: the screen works until the page is closed */ }
    window.KIS.deviceToken = token || null;
}

function deviceApi(path, opts = {}) {
    const token = window.KIS.deviceToken || deviceToken();
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch('/api/v1' + path, { ...opts, headers }).then(response => {
        if (!response.ok) {
            return response.json().catch(() => ({})).then(body => {
                const error = new Error(body.detail || `HTTP error! status: ${response.status}`);
                error.status = response.status;
                throw error;
            });
        }
        return response.json();
    });
}

function renderDisplay(root) {
    if (window.KIS.deviceToken || deviceToken()) {
        renderDisplayBoard(root);
    } else {
        renderDisplayConnect(root);
    }
}

function renderDisplayConnect(root, message = '') {
    root.innerHTML = `
        <div class="card">
            <h2>Connect this device</h2>
            <p>Ask a manager to open <strong>Device Management</strong> and read you the code for this screen.</p>
            <div class="form-group"><label for="pair-code">Code</label>
                <input type="text" id="pair-code" class="pairing-input" maxlength="6" autocomplete="off" autocapitalize="characters" spellcheck="false"></div>
            <button id="pair-btn" class="btn-large">Connect</button>
            <p id="pair-status" class="status-note">${escapeHtml(message)}</p>
        </div>`;
    const input = root.querySelector('#pair-code');
    const connect = () => {
        const code = input.value.trim();
        if (!code) return;
        deviceApi('/devices/pair', { method: 'POST', body: JSON.stringify({ code }) })
            .then(result => {
                setDeviceToken(result.token);
                renderDisplayBoard(root);
            })
            .catch(error => { root.querySelector('#pair-status').textContent = error.message; });
    };
    root.querySelector('#pair-btn').addEventListener('click', connect);
    input.addEventListener('keydown', event => { if (event.key === 'Enter') connect(); });
    input.focus();
}

function renderDisplayBoard(root) {
    root.innerHTML = `
        <div class="card">
            <div class="display-header">
                <h2 id="display-title">Connecting...</h2>
                <button id="display-disconnect" class="btn-large">Disconnect</button>
            </div>
            <p id="display-status" class="status-note"></p>
            <div class="grid-buttons" id="kitchen-columns"></div>
        </div>`;
    root.querySelector('#display-disconnect').addEventListener('click', () => {
        if (!window.confirm('Disconnect this screen? A manager will need to give it a new code.')) return;
        deviceApi('/devices/disconnect', { method: 'POST' }).catch(() => {}).then(() => {
            stopDisplayTimer();
            setDeviceToken(null);
            renderDisplayConnect(root);
        });
    });
    root.querySelector('#kitchen-columns').addEventListener('click', event => {
        const button = event.target.closest('.bump-btn');
        if (!button) return;
        button.disabled = true;
        deviceApi(`/devices/tickets/${button.dataset.orderId}/${button.dataset.track}/bump`, { method: 'POST' })
            .then(() => loadDisplayBoard(root))
            .catch(error => { root.querySelector('#display-status').textContent = `Could not bump: ${error.message}`; });
    });
    loadDisplayBoard(root);
    stopDisplayTimer();
    window.KIS.displayInterval = setInterval(() => loadDisplayBoard(root), 2000);
}

function stopDisplayTimer() {
    if (window.KIS && window.KIS.displayInterval) {
        clearInterval(window.KIS.displayInterval);
        window.KIS.displayInterval = null;
    }
}

function loadDisplayBoard(root) {
    const columns = root.querySelector('#kitchen-columns');
    if (!columns) { stopDisplayTimer(); return; }
    deviceApi('/devices/tickets')
        .then(board => {
            root.querySelector('#display-title').textContent = board.device.name;
            root.querySelector('#display-status').textContent = '';
            columns.innerHTML = Object.entries(board.tracks).map(([track, tickets]) => `
                <div class="kitchen-column">
                    <h3>${escapeHtml(JOB_LABELS[track] || track)}</h3>
                    <div class="ticket-stack">
                        ${tickets.length === 0 ? '<p>No active tickets</p>' : tickets.map(ticket => `
                            <div class="card ticket-card">
                                <p><strong>Seat:</strong> ${escapeHtml(ticket.seat)}</p>
                                <p><strong>Party:</strong> ${escapeHtml(ticket.party_name)}</p>
                                <p><strong>Opened:</strong> ${fmtElapsed(ticket.opened_at)}</p>
                                <div class="order-items">
                                    ${ticket.items.map(item => `
                                        <div class="order-item-card">
                                            <p><strong>${escapeHtml(item.name)}</strong> - Qty: ${item.qty}
                                                ${item.notes ? ` | Notes: ${escapeHtml(item.notes)}` : ''}</p>
                                            <span class="${item.voided ? 'voided-badge' : item.changed ? 'changed-badge' : 'new-badge'}">${item.voided ? 'VOID' : item.changed ? 'CHANGED' : 'NEW'}</span>
                                        </div>`).join('')}
                                </div>
                                <button class="btn-large bump-btn" data-order-id="${ticket.order_id}" data-track="${escapeHtml(track)}">Bump</button>
                            </div>`).join('')}
                    </div>
                </div>`).join('');
        })
        .catch(error => {
            if (error.status === 401) {
                // A manager disconnected, deactivated or re-coded this screen
                stopDisplayTimer();
                setDeviceToken(null);
                renderDisplayConnect(root, 'This screen was disconnected. Enter a new code to reconnect.');
            } else {
                const status = root.querySelector('#display-status');
                if (status) status.textContent = `Lost contact with the server (${error.message}). Retrying...`;
            }
        });
}

// ---------------------------------------------------------------------------------------------
// Sign-in helpers: an employee choosing their own PIN, and the owner's authenticator code
// ---------------------------------------------------------------------------------------------

// The PIN on a new employee card is a starter PIN. Before first use the employee replaces it with
// one only they know. `then` runs with the updated credentials once the new PIN is saved.
function promptOwnPin(credentials, then) {
    const body = openModal('Choose your own PIN', `
        <p>The PIN you were given is a starter PIN. Choose one that only you know.</p>
        <div class="form-group"><label for="own-pin">New PIN (4 or more characters)</label>
            <input type="password" id="own-pin" autocomplete="new-password" inputmode="numeric"></div>
        <div class="form-group"><label for="own-pin-again">New PIN again</label>
            <input type="password" id="own-pin-again" autocomplete="new-password" inputmode="numeric"></div>
        <p id="own-pin-status" class="status-note"></p>
        <button id="own-pin-save" class="btn-large">Save my PIN</button>
        <button id="own-pin-cancel" class="btn-large">Cancel</button>`);
    const status = body.querySelector('#own-pin-status');
    body.querySelector('#own-pin-cancel').addEventListener('click', closeModal);
    body.querySelector('#own-pin-save').addEventListener('click', () => {
        const pin = body.querySelector('#own-pin').value;
        if (pin.length < 4) { status.textContent = 'Use at least 4 characters.'; return; }
        if (pin !== body.querySelector('#own-pin-again').value) { status.textContent = 'The two PINs do not match.'; return; }
        if (pin === credentials.pin) { status.textContent = 'Choose a PIN different from the starter PIN.'; return; }
        api('/auth/change-pin', { method: 'POST', body: JSON.stringify({ code: credentials.code, pin: credentials.pin, new_pin: pin }) })
            .then(() => {
                closeModal();
                const field = document.getElementById('pin');
                if (field) field.value = pin;
                setLoginMessage('Your PIN is saved.');
                then({ ...credentials, pin });
            })
            .catch(error => { status.textContent = error.message; });
    });
    body.querySelector('#own-pin').focus();
}

// Second step for the owner: the 6-digit code from their authenticator app
function promptAuthenticatorCode(message, then) {
    const body = openModal('Authenticator code', `
        <p>Enter the 6-digit code from your authenticator app.</p>
        <div class="form-group"><label for="otp-code">Code</label>
            <input type="text" id="otp-code" class="pairing-input" maxlength="7" inputmode="numeric" autocomplete="one-time-code"></div>
        <p id="otp-status" class="status-note">${escapeHtml(message || '')}</p>
        <button id="otp-go" class="btn-large">Sign in</button>
        <button id="otp-cancel" class="btn-large">Cancel</button>`);
    const input = body.querySelector('#otp-code');
    const submit = () => {
        const otp = input.value.replace(/\D/g, '');
        if (otp.length !== 6) { body.querySelector('#otp-status').textContent = 'The code has 6 digits.'; return; }
        closeModal();
        then(otp);
    };
    body.querySelector('#otp-cancel').addEventListener('click', closeModal);
    body.querySelector('#otp-go').addEventListener('click', submit);
    input.addEventListener('keydown', event => { if (event.key === 'Enter') submit(); });
    input.focus();
}

// ---------------------------------------------------------------------------------------------
// Owner Security: two-step sign-in with an authenticator app
// ---------------------------------------------------------------------------------------------
function renderSecurity(root) {
    root.innerHTML = `
        <div class="card">
            <h2>Sign-in Security</h2>
            <p>With two-step sign-in, signing in takes your PIN <strong>and</strong> a code from an app on your phone.
               It protects the owner's access to the employee database, and it is required to use the
               <strong>Look-in</strong> portal from outside the restaurant.</p>
            <div id="sec-body"><p>Loading...</p></div>
            <p id="sec-status" class="status-note"></p>
            <h3>Your PIN</h3>
            <p>Change the PIN you sign in with.</p>
            <button id="sec-change-pin" class="btn-large">Change my PIN</button>
        </div>`;
    root.querySelector('#sec-change-pin').addEventListener('click', changeMyPin);
    loadSecurity();
}

function changeMyPin() {
    const body = openModal('Change my PIN', `
        <div class="form-group"><label for="my-pin-now">Current PIN</label><input type="password" id="my-pin-now" autocomplete="current-password"></div>
        <div class="form-group"><label for="my-pin-new">New PIN (4 or more characters)</label><input type="password" id="my-pin-new" autocomplete="new-password"></div>
        <div class="form-group"><label for="my-pin-again">New PIN again</label><input type="password" id="my-pin-again" autocomplete="new-password"></div>
        <p id="my-pin-status" class="status-note"></p>
        <button id="my-pin-save" class="btn-large">Save</button>
        <button id="my-pin-cancel" class="btn-large">Cancel</button>`);
    const status = body.querySelector('#my-pin-status');
    body.querySelector('#my-pin-cancel').addEventListener('click', closeModal);
    body.querySelector('#my-pin-save').addEventListener('click', () => {
        const pin = body.querySelector('#my-pin-now').value;
        const next = body.querySelector('#my-pin-new').value;
        if (next.length < 4) { status.textContent = 'Use at least 4 characters.'; return; }
        if (next !== body.querySelector('#my-pin-again').value) { status.textContent = 'The two PINs do not match.'; return; }
        api('/auth/change-pin', { method: 'POST', body: JSON.stringify({ code: state.employee.code, pin, new_pin: next }) })
            .then(() => {
                closeModal();
                document.getElementById('sec-status').textContent = 'Your PIN is changed.';
            })
            .catch(error => { status.textContent = error.message; });
    });
}

function loadSecurity() {
    const box = document.getElementById('sec-body');
    if (!box) return;
    api('/auth/totp')
        .then(info => {
            if (info.enabled) {
                box.innerHTML = `
                    <p><span class="connection connection-ok">Two-step sign-in is ON.</span></p>
                    <p>To move to a new phone, turn it off and set it up again.</p>
                    <div class="form-group"><label for="sec-off-code">Code from your app, to turn it off</label>
                        <input type="text" id="sec-off-code" class="pairing-input" maxlength="7" inputmode="numeric" autocomplete="one-time-code"></div>
                    <button id="sec-off" class="btn-large">Turn off two-step sign-in</button>
                    <p><small>Lost the phone? On the server computer run <code>venv/bin/python -m app.cli reset-two-step ${escapeHtml(state.employee.code)}</code></small></p>`;
                box.querySelector('#sec-off').addEventListener('click', () => {
                    const otp = box.querySelector('#sec-off-code').value.replace(/\D/g, '');
                    api('/auth/totp/disable', { method: 'POST', body: JSON.stringify({ otp }) })
                        .then(() => { document.getElementById('sec-status').textContent = 'Two-step sign-in is off.'; loadSecurity(); })
                        .catch(error => { document.getElementById('sec-status').textContent = error.message; });
                });
            } else {
                box.innerHTML = `
                    <p><span class="connection connection-untested">Two-step sign-in is off.</span></p>
                    <p>You need an authenticator app on your phone. Any one works; these are free and open source:
                       <strong>Aegis</strong> (Android), <strong>2FAS</strong> (Android and iPhone), <strong>Ente Auth</strong> (Android, iPhone and PC).</p>
                    <button id="sec-setup" class="btn-large">Set up two-step sign-in</button>`;
                box.querySelector('#sec-setup').addEventListener('click', startTwoStepSetup);
            }
        })
        .catch(error => { box.innerHTML = `<p class="status-note">Could not load (${escapeHtml(error.message)}).</p>`; });
}

function startTwoStepSetup() {
    const box = document.getElementById('sec-body');
    const status = document.getElementById('sec-status');
    api('/auth/totp/setup', { method: 'POST' })
        .then(setup => {
            status.textContent = '';
            const spaced = setup.secret.replace(/(.{4})/g, '$1 ').trim();
            box.innerHTML = `
                <ol class="setup-steps">
                    <li>Open your authenticator app and add an account.</li>
                    <li>Scan this code with the app, or type the key in by hand.
                        <div id="sec-qr" class="qr-box"></div>
                        <p>Key: <code class="secret-key">${escapeHtml(spaced)}</code></p>
                        <p><a id="sec-link" href="#">Setting up on this same phone? Tap here to open the app.</a></p></li>
                    <li>Enter the 6-digit code the app shows to finish.
                        <div class="form-group"><input type="text" id="sec-on-code" class="pairing-input" maxlength="7" inputmode="numeric" autocomplete="one-time-code"></div>
                        <button id="sec-on" class="btn-large">Turn on two-step sign-in</button>
                        <button id="sec-cancel" class="btn-large">Cancel</button></li>
                </ol>`;
            // The QR code is an SVG the server drew from the key; shown as an image so nothing in it can run
            const image = document.createElement('img');
            image.alt = 'QR code for your authenticator app';
            image.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(setup.qr_svg);
            box.querySelector('#sec-qr').appendChild(image);
            box.querySelector('#sec-link').href = setup.uri;
            box.querySelector('#sec-cancel').addEventListener('click', loadSecurity);
            box.querySelector('#sec-on').addEventListener('click', () => {
                const otp = box.querySelector('#sec-on-code').value.replace(/\D/g, '');
                api('/auth/totp/enable', { method: 'POST', body: JSON.stringify({ otp }) })
                    .then(() => { status.textContent = 'Two-step sign-in is on. You will be asked for a code each time you log in.'; loadSecurity(); })
                    .catch(error => { status.textContent = error.message; });
            });
            box.querySelector('#sec-on-code').focus();
        })
        .catch(error => { status.textContent = error.message; });
}

// ---------------------------------------------------------------------------------------------
// Look-in portal: a read-only, real-time view of today's business for the owner and managers.
// It has its own sign-in (no clock-in needed) and is the one screen meant to be opened from outside.
// ---------------------------------------------------------------------------------------------
const LOOKIN_TOKEN_KEY = 'kisnet.lookinToken';
const LOOKIN_REFRESH_MS = 5000;
let portalMode = 'full';  // 'lookin' when this server is the look-in portal only

function lookinToken() {
    try { return sessionStorage.getItem(LOOKIN_TOKEN_KEY); } catch (error) { return null; }
}

function setLookinToken(token) {
    try {
        if (token) sessionStorage.setItem(LOOKIN_TOKEN_KEY, token); else sessionStorage.removeItem(LOOKIN_TOKEN_KEY);
    } catch (error) { /* storage blocked: the page works until it is closed */ }
}

function lookinApi(path, opts = {}) {
    const headers = { 'Content-Type': 'application/json' };
    const token = lookinToken();
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch('/api/v1' + path, { ...opts, headers }).then(response => {
        if (!response.ok) {
            return response.json().catch(() => ({})).then(body => {
                const error = new Error(typeof body.detail === 'string' ? body.detail : `HTTP error! status: ${response.status}`);
                error.status = response.status;
                error.code = response.headers.get('X-Error-Code');
                throw error;
            });
        }
        return response.json();
    });
}

function renderLookin(root) {
    if (lookinToken()) {
        renderLookinBoard(root);
    } else {
        renderLookinSignIn(root);
    }
}

function renderLookinSignIn(root, message = '') {
    root.innerHTML = `
        <div class="card">
            <h2>Look-in</h2>
            <p>See today's business in real time. For the owner and managers. Sales are view-only; you can clock people out to manage labor.</p>
            <div class="form-group"><label for="lookin-code">Employee code</label>
                <input type="text" id="lookin-code" autocomplete="username" autocapitalize="characters" spellcheck="false"></div>
            <div class="form-group"><label for="lookin-pin">PIN</label>
                <input type="password" id="lookin-pin" autocomplete="current-password"></div>
            <div class="form-group"><label for="lookin-otp">Authenticator code</label>
                <input type="text" id="lookin-otp" class="pairing-input" maxlength="7" inputmode="numeric" autocomplete="one-time-code"></div>
            <button id="lookin-go" class="btn-large">Sign in</button>
            <p id="lookin-status" class="status-note">${escapeHtml(message)}</p>
        </div>`;
    const status = root.querySelector('#lookin-status');
    const submit = () => {
        const code = root.querySelector('#lookin-code').value.trim().toUpperCase();
        const pin = root.querySelector('#lookin-pin').value;
        const otp = root.querySelector('#lookin-otp').value.replace(/\D/g, '');
        if (!code || !pin) { status.textContent = 'Enter your employee code and PIN.'; return; }
        const body = { code, pin };
        if (otp) body.otp = otp;
        lookinApi('/lookin/login', { method: 'POST', body: JSON.stringify(body) })
            .then(result => {
                setLookinToken(result.token);
                renderLookinBoard(root);
            })
            .catch(error => {
                status.textContent = error.code === 'pin_change_required'
                    ? 'Choose your own PIN at the restaurant first, then sign in here.'
                    : error.message;
                root.querySelector('#lookin-otp').value = '';
            });
    };
    root.querySelector('#lookin-go').addEventListener('click', submit);
    root.querySelectorAll('input').forEach(input =>
        input.addEventListener('keydown', event => { if (event.key === 'Enter') submit(); }));
    root.querySelector('#lookin-code').focus();
}

function stopLookinTimer() {
    if (window.KIS && window.KIS.lookinInterval) {
        clearInterval(window.KIS.lookinInterval);
        window.KIS.lookinInterval = null;
    }
}

function renderLookinBoard(root) {
    root.innerHTML = `
        <div class="card">
            <div class="display-header">
                <h2>Today's business</h2>
                <button id="lookin-out" class="btn-large">Sign out</button>
            </div>
            <p id="lookin-updated" class="lookin-updated">Loading...</p>
            <div id="lookin-body"></div>
        </div>`;
    root.querySelector('#lookin-out').addEventListener('click', () => {
        stopLookinTimer();
        lookinApi('/lookin/logout', { method: 'POST' }).catch(() => {}).then(() => {
            setLookinToken(null);
            renderLookinSignIn(root);
        });
    });
    // Labor management: clock one person out
    root.querySelector('#lookin-body').addEventListener('click', event => {
        const button = event.target.closest('.lookin-clock-out');
        if (!button) return;
        const name = button.dataset.name;
        const tables = Number(button.dataset.tables);
        const warning = tables > 0 ? ` They still have ${tables} open table${tables === 1 ? '' : 's'}.` : '';
        if (!window.confirm(`Clock out ${name} now?${warning}`)) return;
        button.disabled = true;
        lookinApi(`/lookin/clock-out/${button.dataset.id}`, { method: 'POST' })
            .then(() => loadLookin(root))
            .catch(error => {
                const updated = root.querySelector('#lookin-updated');
                updated.textContent = `Could not clock out ${name}: ${error.message}`;
                updated.classList.add('status-note');
            });
    });
    loadLookin(root);
    stopLookinTimer();
    window.KIS.lookinInterval = setInterval(() => loadLookin(root), LOOKIN_REFRESH_MS);
}

function loadLookin(root) {
    const box = root.querySelector('#lookin-body');
    if (!box) { stopLookinTimer(); return; }
    const updated = root.querySelector('#lookin-updated');
    lookinApi('/lookin')
        .then(data => {
            const money = cents => `$${(cents / 100).toFixed(2)}`;
            updated.textContent = `Live. Updated ${parseServerTime(data.as_of).toLocaleTimeString()}`;
            updated.classList.remove('status-note');
            box.innerHTML = `
                <div class="stat-row">
                    <div class="stat-card"><span>Sales today</span><strong>${money(data.sales_cents)}</strong></div>
                    <div class="stat-card"><span>Labor today</span><strong>${money(data.labor_cents)}</strong></div>
                    <div class="stat-card"><span>Labor %</span><strong>${data.labor_pct === null ? '-' : data.labor_pct + '%'}</strong></div>
                    <div class="stat-card"><span>Open tickets</span><strong>${data.active_tickets}</strong></div>
                    <div class="stat-card"><span>Open tables</span><strong>${data.open_tables}</strong></div>
                    <div class="stat-card"><span>On the clock</span><strong>${data.on_clock.length}</strong></div>
                </div>
                <h3>On the clock</h3>
                ${data.on_clock.length === 0 ? '<p>Nobody is clocked in.</p>' : `
                <table class="data-table">
                    <thead><tr><th>Name</th><th>Working as</th><th>Clocked in</th><th>Open tables</th><th></th></tr></thead>
                    <tbody>${data.on_clock.map(person => `
                        <tr><td>${escapeHtml(person.name)}</td><td>${escapeHtml(roleLabel(person.position))}</td>
                            <td>${parseServerTime(person.clocked_in_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</td>
                            <td>${person.open_tables || ''}</td>
                            <td><button class="btn-large lookin-clock-out" data-id="${person.employee_id}" data-name="${escapeHtml(person.name)}" data-tables="${person.open_tables}">Clock out</button></td></tr>`).join('')}</tbody>
                </table>`}
                <h3>By the hour</h3>
                ${data.hours.length === 0 ? '<p>No sales or labor yet today.</p>' : `
                <table class="data-table">
                    <thead><tr><th>Hour</th><th>Sales</th><th>Labor</th><th>Labor %</th></tr></thead>
                    <tbody>${data.hours.map(row => `
                        <tr><td>${escapeHtml(row.hour)}</td><td>${money(row.sales_cents)}</td><td>${money(row.labor_cents)}</td>
                            <td>${row.labor_pct === null ? '-' : row.labor_pct + '%'}</td></tr>`).join('')}</tbody>
                </table>`}`;
        })
        .catch(error => {
            if (error.status === 401) {
                stopLookinTimer();
                setLookinToken(null);
                renderLookinSignIn(root, 'Your look-in sign-in has ended. Sign in again.');
            } else {
                updated.textContent = `Lost contact (${error.message}). Showing the last figures; retrying...`;
                updated.classList.add('status-note');
            }
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
                <h3>${escapeHtml(title)}</h3>
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
            <div class="form-group" ${isOwner() ? '' : 'hidden'}>
                <label for="menu-import-file">Import Menu CSV (owner only):</label>
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
                                        <td>${escapeHtml(row.name)}</td>
                                        <td>${escapeHtml(row.category)}</td>
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
                                        <td>${escapeHtml(row.ingredient)}</td>
                                        <td>${escapeHtml(row.unit)}</td>
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
                        <p>Error: ${escapeHtml(error.message)}</p>
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
                            <button class="button-card" data-seat="${escapeHtml(seat.seat)}">
                                ${escapeHtml(seat.seat)}<br>
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
                            <button class="button-card" data-party-id="${party.id}" data-seat="${escapeHtml(party.seat)}"
                                    data-name="${escapeHtml(party.party_name)}">
                                ${escapeHtml(party.seat)}<br>${escapeHtml(party.party_name)}<br>${fmtElapsed(party.opened_at)}
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
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${escapeHtml(error.message)}</p></div>`;
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
                                data-seat="${escapeHtml(seat.seat)}" 
                                data-occupied="${!!seat.party}"
                            >
                                ${escapeHtml(seat.seat)}<br>
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
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${escapeHtml(error.message)}</p></div>`;
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
                            <p><strong>Seat:</strong> ${escapeHtml(ticket.seat)}</p>
                            <p><strong>Party:</strong> ${escapeHtml(ticket.party_name)}</p>
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
            barTicketsContainer.innerHTML = `<p>Error loading tickets: ${escapeHtml(error.message)}</p>`;
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
                            <p><strong>Seat:</strong> ${escapeHtml(ticket.seat)}</p>
                            <p><strong>Party:</strong> ${escapeHtml(ticket.party_name)}</p>
                            <p><strong>Opened:</strong> ${fmtElapsed(ticket.opened_at)}</p>
                            <div class="order-items">
                                ${ticket.items.map(item => {
                                    const statusBadge = item.voided ? 'VOID' : item.changed ? 'CHANGED' : 'NEW';
                                    const statusClass = item.voided ? 'voided-badge' : item.changed ? 'changed-badge' : 'new-badge';
                                    return `
                                        <div class="order-item-card">
                                            <p><strong>${escapeHtml(item.name)}</strong> - Qty: ${item.qty} 
                                                ${item.notes ? ` | Notes: ${escapeHtml(item.notes)}` : ''}
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
            container.innerHTML = `<p>Error loading ${escapeHtml(track)} tickets: ${escapeHtml(error.message)}</p>`;
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
    '/devices': renderDevices,
    '/security': renderSecurity,
    '/lookin': renderLookin,
    '/display': renderDisplay,
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
            <div>Welcome, ${escapeHtml(state.employee.name)} (${escapeHtml(state.employee.role)})</div>
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
const PUBLIC_PATHS = ['/home', '/login', '/timecard', '/display', '/lookin'];

// Menu labels for every screen the menu can open
const MENU_LABELS = {
    '/home': 'Home', '/login': 'Login',
    '/command': 'Command Center', '/reports': 'Reports', '/host': 'Host', '/server': 'Server',
    '/bar': 'Drink Queue', '/barseats': 'Bar Seats', '/kitchen': 'Kitchen', '/timecard': 'Time Card',
    '/summary': 'Daily Summary', '/employees': 'Employees', '/recipes': 'Recipes',
    '/devices': 'Device Management', '/display': 'Connect a Screen', '/security': 'Sign-in Security', '/lookin': 'Look-in'
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
        paths = portalMode === 'lookin' ? ['/lookin'] : ['/home', '/login', '/timecard', '/display', '/lookin'];
    } else if (state.employee.role === 'admin') {
        paths = ['/command', '/summary', '/reports', '/host', '/server', '/barseats', '/bar', '/kitchen', '/timecard', '/security'];
        if (isOwner()) paths = paths.concat(OWNER_PATHS);  // a manager runs the floor; the System section is the owner's
    } else {
        paths = state.employee.role === 'bartender'
            ? ['/barseats', '/bar', '/timecard']
            : [stationFor(state.employee.role), '/timecard'];
    }
    menu.innerHTML = '<h3 class="side-menu-title">Menu</h3>';
    paths.forEach((path, index) => {
        // The owner's System section (Employees, Recipes, Device Management, Owner Security) sits under its own heading
        if (path === OWNER_PATHS[0]) {
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
    if (portalMode === 'lookin' && window.location.hash !== '#/lookin') {
        go('/lookin');
        return;
    }

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

    const path = window.location.hash.slice(1) || '/login';
    if (!SCREENS[path]) {
        go('/login');
        return;
    }
    // Typing an address does not get around access: send people back to their own station
    if (!PUBLIC_PATHS.includes(path) && !canVisit(state.employee.role, path)) {
        go(stationFor(state.employee.role));
        return;
    }
    renderNavBar();
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
    
    // Initial screen load. First ask the server whether it is the full POS or the look-in portal only.
    fetch('/api/v1/portal').then(response => response.json()).catch(() => ({ mode: 'full' })).then(info => {
        portalMode = info.mode === 'lookin' ? 'lookin' : 'full';
        updateScreen();
    });
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
    stopDisplayTimer();
    stopLookinTimer();
    if (window.KIS && window.KIS.devicesInterval) {
        clearInterval(window.KIS.devicesInterval);
        window.KIS.devicesInterval = null;
    }
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
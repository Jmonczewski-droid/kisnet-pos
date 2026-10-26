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
                return response.json().then(err => {
                    throw new Error(err.detail || `HTTP error! status: ${response.status}`);
                });
            }
            return response.json();
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

// Format date helper
function fmtDate(iso) {
    if (!iso) return '';
    // Append 'Z' if no timezone
    if (!iso.includes('Z') && !iso.match(/\+.*|-[0-9]{4}$/)) {
        iso += 'Z';
    }
    const date = new Date(iso);
    return date.toLocaleString();
}

// Format elapsed time helper
function fmtElapsed(iso) {
    if (!iso) return '';
    const date = new Date(iso);
    const now = new Date();
    const diffInSeconds = Math.floor((now - date) / 1000);
    
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
                        
                    ${party.open_order ? `
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
                    
                    ${isServerScreen && !party.open_order ? `
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
            
            // Add event listeners for menu items in a server screen (for creating new order items)
            if (isServerScreen && !party.open_order) {
                document.querySelectorAll('.menu-item-btn').forEach(button => {
                    button.addEventListener('click', function() {
                        const itemId = this.dataset.itemId;
                        const name = this.dataset.name;
                        const category = this.dataset.category;
                        const price = this.dataset.price;
                        
                        // Create input for quantity
                        root.innerHTML += `
                            <div class="card">
                                <h3>Add Item</h3>
                                <div class="form-group">
                                    <label for="qty-input">Quantity:</label>
                                    <input type="number" id="qty-input" min="1" value="1">
                                </div>
                                <div class="form-group">
                                    <label for="notes-input">Notes (optional):</label>
                                    <input type="text" id="notes-input" placeholder="Optional notes">
                                </div>
                                <button id="confirm-add-item-btn" class="btn-large">Add Item to Order</button>
                                <button id="cancel-add-btn" class="btn-large">Cancel</button>
                            </div>
                        `;
                        
                        // Add event listeners for the new inputs
                        document.getElementById('confirm-add-item-btn').addEventListener('click', function() {
                            const qty = parseInt(document.getElementById('qty-input').value);
                            const notes = document.getElementById('notes-input').value || null;
                            
                            if (qty < 1) {
                                alert('Quantity must be at least 1');
                                return;
                            }
                            
                            api(`/api/v1/parties/${party.id}/items`, {
                                method: 'POST',
                                body: JSON.stringify({
                                    items: [{
                                        menu_item_id: parseInt(itemId),
                                        qty: qty,
                                        notes: notes
                                    }]
                                })
                            })
                            .then(() => {
                                // Refresh the server screen after adding item
                                renderServer(root);
                            })
                            .catch(error => {
                                if (error.message.includes('409')) {
                                    alert(`Cannot add item: ${error.message}`);
                                } else {
                                    alert('Error adding item: ' + error.message);
                                }
                                console.error('Error adding item:', error);
                            });
                        });
                        
                        document.getElementById('cancel-add-btn').addEventListener('click', function() {
                            // Refresh the server screen after cancel
                            renderServer(root);
                        });
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
                <h2>KISnet POS Login</h2>
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
    
    api('/auth/clock-in', {
        method: 'POST',
        body: JSON.stringify({ code, pin })
    })
    .then(data => {
        // Store token and employee info
        localStorage.setItem('kisnet.token', data.token);
        state.token = data.token;
        state.employee = data.employee;
        
        // Route based on role
        switch (data.employee.role) {
            case 'admin':
                go('#/command');
                break;
            case 'host':
                go('#/host');
                break;
            case 'server':
                go('#/server');
                break;
            case 'bartender':
                go('#/bar');
                break;
            case 'kitchen':
                go('#/kitchen');
                break;
            default:
                go('#/login');
        }
    })
    .catch(error => {
        alert('Login failed: ' + error.message);
        console.error('Login error:', error);
    });
}

function renderCommand(root) {
    root.innerHTML = '<div class="card"><h2>Command Center (Loading...)</h2></div>';
    
    // Fetch employees on clock
    api('/api/v1/admin/on-clock')
        .then(employees => {
            if (employees.length === 0) {
                root.innerHTML = '<div class="card"><h2>Command Center</h2><p>No employees currently on clock.</p></div>';
                return;
            }
            
            const tableHTML = `
                <div class="card">
                    <h2>Command Center</h2>
                    <table>
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
                        <tbody>
                            ${employees.map(emp => `
                                <tr>
                                    <td>${emp.code}</td>
                                    <td>${emp.name}</td>
                                    <td>${emp.role}</td>
                                    <td>${fmtDate(emp.clocked_in_at)}</td>
                                    <td>${fmtElapsed(emp.clocked_in_at)}</td>
                                    <td><button class="btn-large clock-out-btn" data-employee-id="${emp.id}">Clock Out</button></td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
            
            root.innerHTML = tableHTML;
            
            // Add event listeners for clock out buttons
            document.querySelectorAll('.clock-out-btn').forEach(button => {
                button.addEventListener('click', function() {
                    const employeeId = this.dataset.employeeId;
                    
                    if (confirm('Are you sure you want to clock out this employee?')) {
                        api(`/api/v1/admin/clock-out/${employeeId}`, { method: 'POST' })
                            .then(() => {
                                // Refresh the command screen after successful clock out
                                renderCommand(root);
                            })
                            .catch(error => {
                                alert('Error clocking out employee: ' + error.message);
                                console.error('Error clocking out:', error);
                            });
                    }
                });
            });
        })
        .catch(error => {
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${error.message}</p></div>`;
            console.error('Error loading employees on clock:', error);
        });
    
    // Refresh every 10 seconds
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
function renderHost(root) {
    api('/api/v1/seats')
        .then(seats => {
            root.innerHTML = `
                <div class="card">
                    <h2>Host Station - Table Seats</h2>
                    <div class="grid-buttons" id="seats-grid">
                        ${seats.map(seat => `
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
            `;
            
            // Add event listeners to buttons
            document.querySelectorAll('#seats-grid button').forEach(button => {
                button.addEventListener('click', function() {
                    const seat = this.dataset.seat;
                    const occupied = this.dataset.occupied === 'true';
                    
                    if (occupied) {
                        // Show party details for occupied seat
                        api(`/api/v1/parties/${seat.party.id}`)
                            .then(party => {
                                renderPartyDetails(root, party, 'host');
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
        })
        .catch(error => {
            root.innerHTML = `<div class="card"><h2>Error</h2><p>${error.message}</p></div>`;
            console.error('Error loading seats:', error);
        });
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
    '/kitchen': renderKitchen
};

// Clock out function
function clockOut() {
    api('/auth/clock-out', { method: 'POST' })
        .then(() => {
            // Clear local storage and state
            localStorage.removeItem('kisnet.token');
            state.employee = null;
            state.token = null;
            
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
            <button id="clock-out-btn" class="btn-large">Clock Out</button>
        `;
        
        document.getElementById('app').prepend(topBar);
        
        // Add event listener for clock out button
        document.getElementById('clock-out-btn').addEventListener('click', clockOut);
    } else {
        topBar.innerHTML = '<div>KISnet POS</div>';
        document.getElementById('app').prepend(topBar);
    }
}

// Update screen based on hash
function updateScreen() {
    const root = document.getElementById('app');
    
    // Clear existing content
    if (root) {
        root.innerHTML = '';
        
        // Remove old nav bar if exists
        const existingNavBar = document.querySelector('.top-bar');
        if (existingNavBar) {
            existingNavBar.remove();
        }
        
        // Add main container and sidebar for authenticated screens
        if (state.employee) {
            const container = document.createElement('div');
            container.className = 'container';
            
            // Create sidebar navigation
            const sidebar = document.createElement('div');
            sidebar.className = 'sidebar';
            
            const navItems = [
                { path: '/command', label: 'Command Center' },
                { path: '/reports', label: 'Reports' },
                { path: '/host', label: 'Host' },
                { path: '/server', label: 'Server' },
                { path: '/bar', label: 'Bar' },
                { path: '/kitchen', label: 'Kitchen' }
            ];
            
            if (state.employee.role === 'admin') {
                navItems.forEach(item => {
                    const link = document.createElement('a');
                    link.href = `#${item.path}`;
                    link.className = 'nav-item';
                    link.textContent = item.label;
                    link.addEventListener('click', (e) => {
                        e.preventDefault();
                        go(item.path);
                    });
                    sidebar.appendChild(link);
                });
            } else {
                // For non-admin roles, only show the correct screen
                const roleMap = {
                    'host': '/host',
                    'server': '/server',
                    'bartender': '/bar',
                    'kitchen': '/kitchen'
                };
                
                if (roleMap[state.employee.role]) {
                    const link = document.createElement('a');
                    link.href = `#${roleMap[state.employee.role]}`;
                    link.className = 'nav-item';
                    link.textContent = roleMap[state.employee.role].substring(1).charAt(0).toUpperCase() + roleMap[state.employee.role].substring(2);
                    link.addEventListener('click', (e) => {
                        e.preventDefault();
                        go(roleMap[state.employee.role]);
                    });
                    sidebar.appendChild(link);
                }
            }
            
            const mainContent = document.createElement('div');
            mainContent.className = 'main-content';
            
            // Append to container
            container.appendChild(sidebar);
            container.appendChild(mainContent);
            root.appendChild(container);
            
            // Render navigation bar
            renderNavBar();
            
            // Render current screen  
            const path = window.location.hash.slice(1) || '/login';
            if (SCREENS[path]) {
                // Clear kitchen interval if leaving kitchen screen
                if (window.KIS && window.KIS.kitchenInterval && 
                    (window.location.hash.slice(1) === '/kitchen' || 
                     (window.location.hash.slice(1) !== '/kitchen' && path === '/kitchen'))) {
                    clearKitchenInterval();
                }
                
                // Clear command interval if leaving command screen
                if (window.KIS && window.KIS.commandInterval && 
                    (window.location.hash.slice(1) === '/command' || 
                     (window.location.hash.slice(1) !== '/command' && path === '/command'))) {
                    clearInterval(window.KIS.commandInterval);
                    window.KIS.commandInterval = null;
                }
                
                SCREENS[path](mainContent);
            } else {
                go('/login');  // Redirect to login if invalid path
            }
        } else {
            // Show login screen for unauthenticated users
            const container = document.createElement('div');
            container.className = 'container';
            root.appendChild(container);
            
            // Check if there's a token and attempt auto-login
            const token = localStorage.getItem('kisnet.token');
            if (token) {
                // Try to validate the token
                api('/auth/me')
                    .then(data => {
                        state.employee = data;
                        state.token = token;
                        go('#/command');  // Default route for authenticated user
                    })
                    .catch(() => {
                        // Invalid token, remove and show login
                        localStorage.removeItem('kisnet.token');
                        renderLogin(container);
                    });
            } else {
                // Show login form
                renderLogin(container);
            }
        }
    }
}

// Initialize the app
function init() {
    // Listen for hash changes
    window.addEventListener('hashchange', updateScreen);
    
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
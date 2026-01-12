// Dashboard JavaScript

// State
let orders = [];
let positions = [];
let symbols = [];
let trades = [];
let settlements = [];
let margin = {};
let profitLoss = {};
let currentTab = 'orders';
let currentAccountTab = 'trades';

// URLs
const baseUrl = window.location.origin;
const webhookUrl = baseUrl + '/order';
const webhookUrlReal = baseUrl + '/order?simulation=false';

// Labels
const actionIcons = { 
    long_entry: { icon: '📈', label: '多入', color: '#00ff88' },
    long_exit: { icon: '📤', label: '多出', color: '#00d9ff' },
    short_entry: { icon: '📉', label: '空入', color: '#ff6b6b' },
    short_exit: { icon: '📥', label: '空出', color: '#ffc107' }
};
const actionLabels = { 
    long_entry: '做多進場', 
    long_exit: '做多出場', 
    short_entry: '做空進場', 
    short_exit: '做空出場' 
};
const statusLabels = { 
    pending: '待處理', 
    submitted: '委託中', 
    filled: '已成交', 
    partial_filled: '部分成交',
    cancelled: '已取消',
    failed: '失敗', 
    no_action: '無動作',
    success: '成功'
};
const fillStatusLabels = {
    PendingSubmit: '待送出',
    PreSubmitted: '預送出',
    Submitted: '委託中',
    Filled: '已成交',
    PartFilled: '部分成交',
    Cancelled: '已取消',
    Failed: '失敗'
};
const dirLabels = { buy: '買', sell: '賣', Buy: '買', Sell: '賣' };

// Local Storage Keys
const STORAGE_KEY_AUTH = 'shioaji_dashboard_auth_key';
const STORAGE_KEY_SIMULATION = 'shioaji_dashboard_simulation_mode';

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('webhookUrl').textContent = webhookUrl;
    
    // Load saved credentials from localStorage
    const savedAuthKey = localStorage.getItem(STORAGE_KEY_AUTH);
    if (savedAuthKey) {
        document.getElementById('authKey').value = savedAuthKey;
    }
    
    // Load saved simulation mode preference
    const savedSimMode = localStorage.getItem(STORAGE_KEY_SIMULATION);
    if (savedSimMode !== null) {
        document.getElementById('simulationMode').checked = savedSimMode === 'true';
    }
    
    // Save auth key when changed
    document.getElementById('authKey').addEventListener('input', (e) => {
        localStorage.setItem(STORAGE_KEY_AUTH, e.target.value);
    });
    
    // Save simulation mode when changed
    document.getElementById('simulationMode').addEventListener('change', (e) => {
        localStorage.setItem(STORAGE_KEY_SIMULATION, e.target.checked);
    });
    
    // Load data on Enter key
    document.getElementById('authKey').addEventListener('keypress', (e) => { 
        if (e.key === 'Enter') loadCurrentTab(); 
    });
    
    // Don't auto-fetch symbols on page load - let user click to load
    // This avoids slow initial page load
});

// Trading Mode Toggle
function toggleTradingMode() {
    const toggle = document.getElementById('modeToggle');
    const webhookUrlEl = document.getElementById('webhookUrl');
    const webhookCard = document.getElementById('webhookCard');
    const realWarning = document.getElementById('realTradingWarning');
    const simInfo = document.getElementById('simModeInfo');
    const simLabel = document.getElementById('simLabel');
    const realLabel = document.getElementById('realLabel');
    
    if (toggle.checked) {
        webhookUrlEl.textContent = webhookUrlReal;
        webhookCard.classList.add('real-trading-mode');
        realWarning.style.display = 'block';
        simInfo.style.display = 'none';
        simLabel.style.color = '#71717a';
        realLabel.style.color = '#ef4444';
        realLabel.style.fontWeight = '600';
        simLabel.style.fontWeight = 'normal';
    } else {
        webhookUrlEl.textContent = webhookUrl;
        webhookCard.classList.remove('real-trading-mode');
        realWarning.style.display = 'none';
        simInfo.style.display = 'block';
        simLabel.style.color = '#22c55e';
        realLabel.style.color = '#71717a';
        simLabel.style.fontWeight = '600';
        realLabel.style.fontWeight = 'normal';
    }
}

function copyWebhookUrl() {
    const toggle = document.getElementById('modeToggle');
    const url = toggle.checked ? webhookUrlReal : webhookUrl;
    navigator.clipboard.writeText(url).then(() => {
        const btn = document.querySelector('#webhookCodeBlock .copy-btn');
        const original = btn.textContent;
        btn.textContent = '已複製！';
        btn.style.background = '#22c55e';
        setTimeout(() => {
            btn.textContent = original;
            btn.style.background = '';
        }, 2000);
    });
}

// Tab Navigation
function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector(`.tab[onclick="switchTab('${tab}')"]`).classList.add('active');
    document.getElementById(`${tab}-tab`).classList.add('active');
}

function switchAccountTab(tab) {
    currentAccountTab = tab;
    document.querySelectorAll('.sub-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.sub-tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector(`.sub-tab[onclick="switchAccountTab('${tab}')"]`).classList.add('active');
    document.getElementById(`${tab}-subtab`).classList.add('active');
}

function loadCurrentTab() {
    if (currentTab === 'orders') fetchOrders();
    else if (currentTab === 'positions') fetchPositions();
    else if (currentTab === 'account') fetchAccountData();
    else if (currentTab === 'symbols') fetchSymbols();
}

// Orders
async function fetchOrders() {
    const authKey = document.getElementById('authKey').value;
    if (!authKey) { showError('請輸入驗證金鑰'); return; }
    
    const status = document.getElementById('filterStatus').value;
    const action = document.getElementById('filterAction').value;
    const symbol = document.getElementById('filterSymbol').value;
    
    let url = '/orders?limit=500';
    if (status) url += `&status=${status}`;
    if (action) url += `&action=${action}`;
    if (symbol) url += `&symbol=${symbol}`;
    
    document.getElementById('ordersTable').innerHTML = '<div class="loading">載入中...</div>';
    hideError();
    
    try {
        const response = await fetch(url, { headers: { 'X-Auth-Key': authKey } });
        if (!response.ok) throw new Error(response.status === 401 ? '驗證金鑰無效' : '載入失敗');
        orders = await response.json();
        renderOrdersTable();
        updateOrderStats();
    } catch (error) {
        showError(error.message);
        document.getElementById('ordersTable').innerHTML = '<div class="empty">載入失敗</div>';
    }
}

function renderOrdersTable() {
    if (orders.length === 0) {
        document.getElementById('ordersTable').innerHTML = '<div class="empty">無委託紀錄</div>';
        return;
    }
    
    let html = `<table><thead><tr>
        <th style="width:10%">時間</th>
        <th style="width:4%">#</th>
        <th style="width:12%">商品</th>
        <th style="width:7%">動作</th>
        <th style="width:5%">口數</th>
        <th style="width:8%">狀態</th>
        <th style="width:13%">成交</th>
        <th style="width:37%">訊息</th>
        <th style="width:4%"></th>
    </tr></thead><tbody>`;
    
    for (const order of orders) {
        const d = new Date(order.created_at);
        const date = `${d.getMonth()+1}/${d.getDate()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
        
        const statusClass = order.status === 'filled' ? 'status-success' : 
                           order.status === 'failed' ? 'status-failed' :
                           order.status === 'cancelled' || order.status === 'no_action' ? 'status-no_action' :
                           'status-pending';
        const statusText = statusLabels[order.status] || order.status;
        
        const fillInfo = order.fill_quantity 
            ? `${order.fill_quantity}口 @ ${order.fill_price?.toLocaleString() || '-'}` 
            : '-';
        
        const act = actionIcons[order.action] || { icon: '●', label: order.action, color: '#a1a1aa' };
        
        const canRecheck = ['submitted', 'pending', 'partial_filled'].includes(order.status);
        const recheckBtn = canRecheck 
            ? `<button class="recheck-btn" onclick="recheckOrder(${order.id})" title="重新查詢狀態">🔄</button>`
            : '';
        
        // Error message - truncate if too long
        const errorMsg = order.error_message 
            ? (order.error_message.length > 50 
                ? `<span title="${order.error_message}" style="color:#ff6b6b;font-size:0.8rem;cursor:help">${order.error_message.substring(0, 50)}...</span>`
                : `<span style="color:#ff6b6b;font-size:0.8rem">${order.error_message}</span>`)
            : '<span style="color:#52525b">-</span>';
        
        html += `<tr id="order-row-${order.id}">
            <td style="color:#a1a1aa;font-size:0.8rem;font-family:'Consolas',monospace">${date}</td>
            <td style="color:#71717a;font-size:0.8rem">${order.id}</td>
            <td>
                <div style="font-family:'Consolas',monospace">
                    <span style="color:#00d9ff;font-weight:600;font-size:0.85rem">${order.symbol}</span>
                    ${order.code && order.code !== order.symbol ? `<br><span style="color:#71717a;font-size:0.7rem">${order.code}</span>` : ''}
                </div>
            </td>
            <td>
                <span style="color:${act.color};font-size:0.85rem" title="${actionLabels[order.action] || order.action}">${act.icon}${act.label}</span>
            </td>
            <td style="text-align:center;font-weight:600">${order.quantity}</td>
            <td><span class="status ${statusClass}">${statusText}</span></td>
            <td style="font-family:'Consolas',monospace;font-size:0.8rem">${fillInfo}</td>
            <td style="max-width:200px;overflow:hidden;text-overflow:ellipsis">${errorMsg}</td>
            <td>${recheckBtn}</td>
        </tr>`;
    }
    html += '</tbody></table>';
    document.getElementById('ordersTable').innerHTML = html;
}

async function recheckOrder(orderId) {
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '⏳';
    
    const authKey = document.getElementById('authKey').value;
    const simulationMode = document.getElementById('simulationMode').checked;
    
    if (!authKey) {
        alert('請先輸入驗證金鑰');
        btn.disabled = false;
        btn.textContent = '🔄';
        return;
    }
    
    try {
        const response = await fetch(`/orders/${orderId}/recheck?simulation=${simulationMode}`, {
            method: 'POST',
            headers: { 'X-Auth-Key': authKey }
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.detail || '查詢失敗');
        }
        
        let msg = `訂單 #${orderId} 狀態更新:\n`;
        msg += `• 狀態: ${result.previous_status} → ${result.current_status}\n`;
        msg += `• 交易所狀態: ${result.current_fill_status}\n`;
        if (result.fill_quantity > 0) {
            msg += `• 成交: ${result.fill_quantity} 口 @ ${result.fill_price?.toFixed(2) || '-'}\n`;
        }
        if (result.deals && result.deals.length > 0) {
            msg += `• 成交明細: ${result.deals.length} 筆`;
        }
        
        alert(msg);
        await fetchOrders();
        
    } catch (error) {
        alert(`查詢失敗: ${error.message}`);
        btn.disabled = false;
        btn.textContent = '🔄';
    }
}

function updateOrderStats() {
    document.getElementById('statTotal').textContent = orders.length;
    document.getElementById('statSuccess').textContent = orders.filter(o => o.status === 'filled' || o.status === 'success').length;
    document.getElementById('statFailed').textContent = orders.filter(o => o.status === 'failed').length;
}

// Positions
async function fetchPositions() {
    const authKey = document.getElementById('authKey').value;
    if (!authKey) { showError('請輸入驗證金鑰'); return; }
    
    document.getElementById('positionsTable').innerHTML = '<div class="loading">載入中...</div>';
    hideError();
    
    try {
        const response = await fetch('/positions', { headers: { 'X-Auth-Key': authKey } });
        if (!response.ok) throw new Error(response.status === 401 ? '驗證金鑰無效' : '載入失敗');
        const data = await response.json();
        positions = data.positions;
        renderPositionsTable();
        updatePositionStats();
    } catch (error) {
        showError(error.message);
        document.getElementById('positionsTable').innerHTML = '<div class="empty">載入失敗</div>';
    }
}

function renderPositionsTable() {
    if (positions.length === 0) {
        document.getElementById('positionsTable').innerHTML = '<div class="empty">目前無持倉</div>';
        return;
    }
    
    let html = `<table><thead><tr>
        <th>商品</th>
        <th style="width:70px">方向</th>
        <th style="width:60px">口數</th>
        <th>均價</th>
        <th>現價</th>
        <th>損益</th>
    </tr></thead><tbody>`;
    
    for (const pos of positions) {
        const pnlClass = pos.pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
        const isLong = pos.direction.toLowerCase() === 'buy';
        const dirIcon = isLong ? '🟢' : '🔴';
        const dirText = isLong ? '多' : '空';
        const dirColor = isLong ? '#00ff88' : '#ff6b6b';
        
        html += `<tr>
            <td>
                <div style="font-family:'Consolas',monospace">
                    <span style="color:#00d9ff;font-weight:600">${pos.symbol}</span>
                    ${pos.code && pos.code !== pos.symbol ? `<span style="color:#71717a;font-size:0.75rem;margin-left:4px">${pos.code}</span>` : ''}
                </div>
            </td>
            <td><span style="color:${dirColor}">${dirIcon} ${dirText}</span></td>
            <td style="text-align:center;font-weight:600">${pos.quantity}</td>
            <td style="font-family:'Consolas',monospace">${pos.price.toLocaleString()}</td>
            <td style="font-family:'Consolas',monospace">${pos.last_price.toLocaleString()}</td>
            <td class="${pnlClass}" style="font-weight:600">${pos.pnl >= 0 ? '+' : ''}${pos.pnl.toLocaleString()}</td>
        </tr>`;
    }
    html += '</tbody></table>';
    document.getElementById('positionsTable').innerHTML = html;
}

function updatePositionStats() {
    const totalPnl = positions.reduce((sum, p) => sum + p.pnl, 0);
    document.getElementById('posCount').textContent = positions.length;
    document.getElementById('totalPnl').textContent = (totalPnl >= 0 ? '+' : '') + totalPnl.toLocaleString();
    const pnlCard = document.getElementById('pnlCard');
    pnlCard.className = 'stat-card ' + (totalPnl >= 0 ? 'pnl-positive' : 'pnl-negative');
}

// Symbols
async function fetchSymbols() {
    const simulationMode = document.getElementById('simulationMode').checked;
    document.getElementById('symbolsTable').innerHTML = '<div class="loading">載入中...</div>';
    
    try {
        const response = await fetch(`/symbols?simulation=${simulationMode}`);
        if (!response.ok) throw new Error('無法取得商品列表');
        
        const data = await response.json();
        symbols = data.symbols || [];
        renderSymbolsTable();
        updateSymbolStats();
        hideError();
    } catch (error) {
        document.getElementById('symbolsTable').innerHTML = `<div class="empty" style="color:#ff6b6b">載入失敗: ${error.message}</div>`;
    }
}

function filterSymbols() {
    const search = document.getElementById('symbolSearch').value.toLowerCase();
    const filtered = symbols.filter(s => 
        s.symbol.toLowerCase().includes(search) || 
        s.code.toLowerCase().includes(search) ||
        s.name.toLowerCase().includes(search)
    );
    renderSymbolsTable(filtered);
}

function renderSymbolsTable(list = symbols) {
    if (list.length === 0) {
        document.getElementById('symbolsTable').innerHTML = '<div class="empty">無符合的商品</div>';
        return;
    }
    
    let html = `<table>
        <thead>
            <tr>
                <th style="width:25%">Symbol (用於下單)</th>
                <th style="width:20%">Code (交易所代碼)</th>
                <th style="width:40%">名稱</th>
                <th style="width:15%">操作</th>
            </tr>
        </thead>
        <tbody>`;
    for (const item of list) {
        html += `<tr>
            <td><strong style="color: #00d9ff; font-family: 'Consolas', monospace;">${item.symbol}</strong></td>
            <td style="color: #a1a1aa; font-family: 'Consolas', monospace;">${item.code}</td>
            <td>${item.name}</td>
            <td><button class="recheck-btn" onclick="copySymbol('${item.symbol}')">📋 複製</button></td>
        </tr>`;
    }
    html += '</tbody></table>';
    document.getElementById('symbolsTable').innerHTML = html;
}

function copySymbol(symbol) {
    navigator.clipboard.writeText(symbol).then(() => {
        const btn = event.target;
        const original = btn.textContent;
        btn.textContent = '✓ 已複製';
        btn.style.background = 'rgba(0, 255, 136, 0.3)';
        btn.style.borderColor = '#00ff88';
        setTimeout(() => {
            btn.textContent = original;
            btn.style.background = '';
            btn.style.borderColor = '';
        }, 1500);
    });
}

function updateSymbolStats() {
    document.getElementById('symbolCount').textContent = symbols.length;
}

// Account Data
async function fetchAccountData() {
    const authKey = document.getElementById('authKey').value;
    const simulationMode = document.getElementById('simulationMode').checked;
    
    if (!authKey) { showError('請輸入驗證金鑰'); return; }
    
    hideError();
    
    // Fetch all account data in parallel, handle errors individually
    const headers = { 'X-Auth-Key': authKey };
    const simParam = `?simulation=${simulationMode}`;
    
    // Use Promise.allSettled to handle partial failures
    const [marginResult, pnlResult, tradesResult, settlementsResult] = await Promise.allSettled([
        fetch(`/margin${simParam}`, { headers }).then(r => r.ok ? r.json() : Promise.reject(r)),
        fetch(`/profit-loss${simParam}`, { headers }).then(r => r.ok ? r.json() : Promise.reject(r)),
        fetch(`/trades${simParam}`, { headers }).then(r => r.ok ? r.json() : Promise.reject(r)),
        fetch(`/settlements${simParam}`, { headers }).then(r => r.ok ? r.json() : Promise.reject(r))
    ]);
    
    // Process results, use defaults for failed requests
    margin = marginResult.status === 'fulfilled' ? marginResult.value : {};
    profitLoss = pnlResult.status === 'fulfilled' ? pnlResult.value : {};
    const tradesData = tradesResult.status === 'fulfilled' ? tradesResult.value : { trades: [] };
    const settlementsData = settlementsResult.status === 'fulfilled' ? settlementsResult.value : { settlements: [] };
    
    trades = tradesData.trades || [];
    settlements = settlementsData.settlements || [];
    
    // Check if critical data failed
    if (marginResult.status === 'rejected' && pnlResult.status === 'rejected') {
        showError('載入帳戶資料失敗，請確認驗證金鑰是否正確');
    }
    
    renderAccountStats();
    renderTradesTable();
    renderSettlementsTable();
}

function renderAccountStats() {
    // Margin stats
    const accountBalance = margin.account_balance || 0;
    const availableMargin = margin.available_margin || 0;
    
    document.getElementById('accountBalance').textContent = 
        accountBalance.toLocaleString();
    document.getElementById('availableMargin').textContent = 
        availableMargin.toLocaleString();
    
    // P&L stats
    const realized = profitLoss.realized_pnl || 0;
    const unrealized = profitLoss.unrealized_pnl || 0;
    
    document.getElementById('realizedPnl').textContent = 
        (realized >= 0 ? '+' : '') + realized.toLocaleString();
    document.getElementById('unrealizedPnl').textContent = 
        (unrealized >= 0 ? '+' : '') + unrealized.toLocaleString();
    
    // Update card colors
    const realizedCard = document.getElementById('realizedPnlCard');
    const unrealizedCard = document.getElementById('unrealizedPnlCard');
    
    realizedCard.className = 'stat-card ' + (realized >= 0 ? 'pnl-positive' : 'pnl-negative');
    unrealizedCard.className = 'stat-card ' + (unrealized >= 0 ? 'pnl-positive' : 'pnl-negative');
    
    // Show info message if all data is zero
    if (accountBalance === 0 && realized === 0 && unrealized === 0 && trades.length === 0) {
        const infoMsg = document.createElement('div');
        infoMsg.className = 'alert alert-info';
        infoMsg.style.marginTop = '1rem';
        infoMsg.innerHTML = '💡 <strong>提示：</strong>模擬帳戶目前無交易資料。請先執行交易後再查看帳戶資訊。';
        
        const statsDiv = document.getElementById('accountStats');
        const existingAlert = statsDiv.nextElementSibling;
        if (existingAlert && existingAlert.classList.contains('alert')) {
            existingAlert.remove();
        }
        statsDiv.after(infoMsg);
    }
}

function renderTradesTable() {
    if (trades.length === 0) {
        document.getElementById('tradesTable').innerHTML = '<div class="empty">無成交紀錄</div>';
        return;
    }
    
    let html = `<table><thead><tr>
        <th style="width:15%">時間</th>
        <th style="width:15%">合約</th>
        <th style="width:10%">動作</th>
        <th style="width:10%">數量</th>
        <th style="width:15%">價格</th>
        <th style="width:35%">訂單ID</th>
    </tr></thead><tbody>`;
    
    for (const trade of trades) {
        const ts = trade.ts ? new Date(trade.ts * 1000).toLocaleString('zh-TW') : '-';
        const actionColor = trade.action.toLowerCase().includes('buy') ? '#00ff88' : '#ff6b6b';
        const actionText = trade.action.toLowerCase().includes('buy') ? '買' : '賣';
        
        html += `<tr>
            <td style="font-size:0.85rem;color:#a1a1aa">${ts}</td>
            <td style="font-family:'Consolas',monospace;color:#00d9ff">${trade.code}</td>
            <td><span style="color:${actionColor};font-weight:600">${actionText}</span></td>
            <td style="text-align:center;font-weight:600">${trade.quantity}</td>
            <td style="font-family:'Consolas',monospace">${trade.price.toLocaleString()}</td>
            <td style="font-family:'Consolas',monospace;font-size:0.8rem;color:#71717a">${trade.order_id || '-'}</td>
        </tr>`;
    }
    html += '</tbody></table>';
    document.getElementById('tradesTable').innerHTML = html;
}

function renderSettlementsTable() {
    if (settlements.length === 0) {
        document.getElementById('settlementsTable').innerHTML = '<div class="empty">無結算資料</div>';
        return;
    }
    
    let html = `<table><thead><tr>
        <th style="width:20%">日期</th>
        <th style="width:25%">結算金額</th>
        <th style="width:25%">T 日資金</th>
        <th style="width:30%">T+1 日資金</th>
    </tr></thead><tbody>`;
    
    for (const settlement of settlements) {
        html += `<tr>
            <td style="font-family:'Consolas',monospace">${settlement.date}</td>
            <td style="font-weight:600">${settlement.amount.toLocaleString()}</td>
            <td>${settlement.T_money.toLocaleString()}</td>
            <td>${settlement.T1_money.toLocaleString()}</td>
        </tr>`;
    }
    html += '</tbody></table>';
    document.getElementById('settlementsTable').innerHTML = html;
}

// Utilities
function exportCSV() {
    const authKey = document.getElementById('authKey').value;
    if (!authKey) { showError('請輸入驗證金鑰'); return; }
    window.open('/orders/export?format=csv', '_blank');
}

function copyToClipboard(btn, text) {
    navigator.clipboard.writeText(text).then(() => {
        const original = btn.textContent;
        btn.textContent = '已複製！';
        btn.style.color = '#00ff88';
        setTimeout(() => { btn.textContent = original; btn.style.color = ''; }, 2000);
    });
}

function showError(msg) { 
    const el = document.getElementById('errorMsg'); 
    el.textContent = msg; 
    el.style.display = 'block'; 
}

function hideError() { 
    document.getElementById('errorMsg').style.display = 'none'; 
}



// ===== Trading Panel Functions =====

let tradingSymbols = [];
let selectedSymbolInfo = null;

// Initialize trading panel when tab is switched
function initTradingPanel() {
    updateTradingModeDisplay();
    loadTradingSymbols();
    refreshPositions();
    refreshAccountSummary();
    loadRecentOrders();
}

// Update trading mode display
function updateTradingModeDisplay() {
    const simulationMode = document.getElementById('simulationMode').checked;
    const badge = document.getElementById('tradingModeBadge');
    const text = document.getElementById('tradingModeText');
    const dot = badge.querySelector('.mode-dot');
    
    if (simulationMode) {
        badge.classList.remove('real-mode');
        text.textContent = '模擬模式';
        dot.classList.remove('real');
        dot.classList.add('simulation');
    } else {
        badge.classList.add('real-mode');
        text.textContent = '實盤模式';
        dot.classList.add('real');
        dot.classList.remove('simulation');
    }
}

// Load trading symbols
async function loadTradingSymbols() {
    const simulationMode = document.getElementById('simulationMode').checked;
    
    try {
        const response = await fetch(`/symbols?simulation=${simulationMode}`);
        if (!response.ok) throw new Error('Failed to load symbols');
        
        const data = await response.json();
        tradingSymbols = data.symbols || [];
        
        // Update symbol selector
        const select = document.getElementById('tradingSymbol');
        select.innerHTML = '<option value="">-- 選擇商品 --</option>';
        
        // Group by product type
        const tmfGroup = document.createElement('optgroup');
        tmfGroup.label = '微型台指 (TMF)';
        
        const mxfGroup = document.createElement('optgroup');
        mxfGroup.label = '小台指 (MXF)';
        
        const txfGroup = document.createElement('optgroup');
        txfGroup.label = '大台指 (TXF)';
        
        const otherGroup = document.createElement('optgroup');
        otherGroup.label = '其他';
        
        tradingSymbols.forEach(s => {
            const option = document.createElement('option');
            option.value = s.symbol;
            option.textContent = `${s.symbol} - ${s.name}`;
            option.dataset.info = JSON.stringify(s);
            
            if (s.symbol.startsWith('TMF')) {
                tmfGroup.appendChild(option);
            } else if (s.symbol.startsWith('MXF')) {
                mxfGroup.appendChild(option);
            } else if (s.symbol.startsWith('TXF')) {
                txfGroup.appendChild(option);
            } else {
                otherGroup.appendChild(option);
            }
        });
        
        if (tmfGroup.children.length > 0) select.appendChild(tmfGroup);
        if (mxfGroup.children.length > 0) select.appendChild(mxfGroup);
        if (txfGroup.children.length > 0) select.appendChild(txfGroup);
        if (otherGroup.children.length > 0) select.appendChild(otherGroup);
        
        // Select first TMF symbol by default (微型台指)
        if (tmfGroup.children.length > 0) {
            select.value = tmfGroup.children[0].value;
            onSymbolChange();
        } else if (mxfGroup.children.length > 0) {
            select.value = mxfGroup.children[0].value;
            onSymbolChange();
        }
        
    } catch (error) {
        console.error('Error loading symbols:', error);
    }
}

function refreshSymbols() {
    loadTradingSymbols();
}

// Handle symbol change
async function onSymbolChange() {
    const select = document.getElementById('tradingSymbol');
    const symbol = select.value;
    
    if (!symbol) {
        resetQuoteDisplay();
        return;
    }
    
    // Get symbol info
    const simulationMode = document.getElementById('simulationMode').checked;
    
    try {
        const response = await fetch(`/symbols/${symbol}?simulation=${simulationMode}`);
        if (response.ok) {
            selectedSymbolInfo = await response.json();
            updateQuoteDisplay(selectedSymbolInfo);
        }
    } catch (error) {
        console.error('Error fetching symbol info:', error);
    }
}

function updateQuoteDisplay(info) {
    document.getElementById('currentPrice').textContent = info.reference?.toLocaleString() || '--';
    document.getElementById('limitUp').textContent = info.limit_up?.toLocaleString() || '--';
    document.getElementById('limitDown').textContent = info.limit_down?.toLocaleString() || '--';
    document.getElementById('refPrice').textContent = info.reference?.toLocaleString() || '--';
}

function resetQuoteDisplay() {
    document.getElementById('currentPrice').textContent = '--';
    document.getElementById('limitUp').textContent = '--';
    document.getElementById('limitDown').textContent = '--';
    document.getElementById('refPrice').textContent = '--';
    selectedSymbolInfo = null;
}

// Quantity controls
function adjustQty(delta) {
    const input = document.getElementById('orderQuantity');
    let value = parseInt(input.value) || 1;
    value = Math.max(1, Math.min(100, value + delta));
    input.value = value;
}

function setQty(qty) {
    document.getElementById('orderQuantity').value = qty;
}

// Place order
async function placeOrder(action) {
    const authKey = document.getElementById('authKey').value;
    const symbol = document.getElementById('tradingSymbol').value;
    const quantity = parseInt(document.getElementById('orderQuantity').value) || 1;
    const simulationMode = document.getElementById('simulationMode').checked;
    
    if (!authKey) {
        showOrderStatus('error', '請先輸入驗證金鑰');
        return;
    }
    
    if (!symbol) {
        showOrderStatus('error', '請選擇交易商品');
        return;
    }
    
    // Confirm for real trading
    if (!simulationMode) {
        const actionText = actionLabels[action] || action;
        if (!confirm(`⚠️ 實盤交易確認\n\n動作: ${actionText}\n商品: ${symbol}\n口數: ${quantity}\n\n確定要執行嗎？`)) {
            return;
        }
    }
    
    showOrderStatus('pending', '委託處理中...');
    
    try {
        const response = await fetch(`/order?simulation=${simulationMode}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Auth-Key': authKey
            },
            body: JSON.stringify({
                action: action,
                symbol: symbol,
                quantity: quantity
            })
        });
        
        const result = await response.json();
        
        if (!response.ok) {
            throw new Error(result.detail || '下單失敗');
        }
        
        if (result.status === 'no_action') {
            showOrderStatus('info', result.message || '無需執行動作');
        } else {
            showOrderStatus('success', `委託成功！訂單 #${result.order_id}`);
        }
        
        // Refresh data
        setTimeout(() => {
            refreshPositions();
            loadRecentOrders();
        }, 1000);
        
    } catch (error) {
        showOrderStatus('error', error.message);
    }
}

// Close all positions
async function closeAllPositions() {
    const authKey = document.getElementById('authKey').value;
    const simulationMode = document.getElementById('simulationMode').checked;
    
    if (!authKey) {
        showOrderStatus('error', '請先輸入驗證金鑰');
        return;
    }
    
    if (!confirm('確定要平倉所有持倉嗎？')) {
        return;
    }
    
    showOrderStatus('pending', '平倉處理中...');
    
    try {
        // Get current positions
        const posResponse = await fetch(`/positions?simulation=${simulationMode}`, {
            headers: { 'X-Auth-Key': authKey }
        });
        
        if (!posResponse.ok) throw new Error('無法取得持倉資料');
        
        const posData = await posResponse.json();
        const positions = posData.positions || [];
        
        if (positions.length === 0) {
            showOrderStatus('info', '目前無持倉');
            return;
        }
        
        // Close each position
        let closedCount = 0;
        for (const pos of positions) {
            const action = pos.direction.toLowerCase() === 'buy' ? 'long_exit' : 'short_exit';
            
            const response = await fetch(`/order?simulation=${simulationMode}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Auth-Key': authKey
                },
                body: JSON.stringify({
                    action: action,
                    symbol: pos.symbol,
                    quantity: pos.quantity
                })
            });
            
            if (response.ok) closedCount++;
        }
        
        showOrderStatus('success', `已平倉 ${closedCount} 筆持倉`);
        
        setTimeout(() => {
            refreshPositions();
            loadRecentOrders();
        }, 1000);
        
    } catch (error) {
        showOrderStatus('error', error.message);
    }
}

function showOrderStatus(type, message) {
    const statusDiv = document.getElementById('orderStatus');
    const iconEl = document.getElementById('statusIcon');
    const textEl = document.getElementById('statusText');
    
    statusDiv.style.display = 'flex';
    statusDiv.className = 'order-status ' + type;
    
    const icons = {
        pending: '⏳',
        success: '✅',
        error: '❌',
        info: 'ℹ️'
    };
    
    iconEl.textContent = icons[type] || '●';
    textEl.textContent = message;
    
    // Auto hide after 5 seconds for success/info
    if (type === 'success' || type === 'info') {
        setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 5000);
    }
}

// Refresh positions for trading panel
async function refreshPositions() {
    const authKey = document.getElementById('authKey').value;
    const simulationMode = document.getElementById('simulationMode').checked;
    
    if (!authKey) return;
    
    try {
        const response = await fetch(`/positions?simulation=${simulationMode}`, {
            headers: { 'X-Auth-Key': authKey }
        });
        
        if (!response.ok) return;
        
        const data = await response.json();
        const positions = data.positions || [];
        
        const container = document.getElementById('currentPositionDisplay');
        
        if (positions.length === 0) {
            container.innerHTML = '<div class="no-position">無持倉</div>';
            return;
        }
        
        let html = '';
        for (const pos of positions) {
            const isLong = pos.direction.toLowerCase() === 'buy';
            const dirClass = isLong ? 'long' : 'short';
            const dirText = isLong ? '多' : '空';
            const pnlClass = pos.pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
            
            html += `
                <div class="position-item">
                    <div>
                        <span class="position-symbol">${pos.symbol}</span>
                        <span class="position-direction ${dirClass}">${dirText}</span>
                    </div>
                    <div>
                        <span class="position-qty">${pos.quantity}口</span>
                        <span class="position-pnl ${pnlClass}">${pos.pnl >= 0 ? '+' : ''}${pos.pnl.toLocaleString()}</span>
                    </div>
                </div>
            `;
        }
        
        container.innerHTML = html;
        
    } catch (error) {
        console.error('Error refreshing positions:', error);
    }
}

// Refresh account summary
async function refreshAccountSummary() {
    const authKey = document.getElementById('authKey').value;
    const simulationMode = document.getElementById('simulationMode').checked;
    
    if (!authKey) return;
    
    try {
        const response = await fetch(`/margin?simulation=${simulationMode}`, {
            headers: { 'X-Auth-Key': authKey }
        });
        
        if (!response.ok) return;
        
        const margin = await response.json();
        
        document.getElementById('tradingMargin').textContent = 
            (margin.available_margin || 0).toLocaleString() + ' 元';
        
        // Get positions for unrealized P&L
        const posResponse = await fetch(`/positions?simulation=${simulationMode}`, {
            headers: { 'X-Auth-Key': authKey }
        });
        
        if (posResponse.ok) {
            const posData = await posResponse.json();
            const positions = posData.positions || [];
            const totalPnl = positions.reduce((sum, p) => sum + (p.pnl || 0), 0);
            
            const pnlEl = document.getElementById('tradingPnl');
            pnlEl.textContent = (totalPnl >= 0 ? '+' : '') + totalPnl.toLocaleString() + ' 元';
            pnlEl.className = 'value ' + (totalPnl >= 0 ? 'pnl-positive' : 'pnl-negative');
        }
        
        document.getElementById('tradingRisk').textContent = 
            (margin.risk_indicator || 0).toFixed(2) + '%';
        
    } catch (error) {
        console.error('Error refreshing account:', error);
    }
}

// Load recent orders
async function loadRecentOrders() {
    const authKey = document.getElementById('authKey').value;
    
    if (!authKey) return;
    
    try {
        const response = await fetch('/orders?limit=5', {
            headers: { 'X-Auth-Key': authKey }
        });
        
        if (!response.ok) return;
        
        const orders = await response.json();
        const container = document.getElementById('recentOrdersList');
        
        if (orders.length === 0) {
            container.innerHTML = '<div class="no-orders">尚無委託</div>';
            return;
        }
        
        let html = '';
        for (const order of orders) {
            const time = new Date(order.created_at);
            const timeStr = `${time.getHours().toString().padStart(2, '0')}:${time.getMinutes().toString().padStart(2, '0')}`;
            
            html += `
                <div class="recent-order-item">
                    <span class="order-action ${order.action}">${actionIcons[order.action]?.label || order.action}</span>
                    <span>${order.symbol}</span>
                    <span>${order.quantity}口</span>
                    <span class="status ${order.status === 'filled' ? 'status-success' : order.status === 'failed' ? 'status-failed' : 'status-pending'}">${statusLabels[order.status] || order.status}</span>
                    <span class="order-time">${timeStr}</span>
                </div>
            `;
        }
        
        container.innerHTML = html;
        
    } catch (error) {
        console.error('Error loading recent orders:', error);
    }
}

// Override switchTab to initialize trading panel
const originalSwitchTab = switchTab;
switchTab = function(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    document.querySelector(`.tab[onclick="switchTab('${tab}')"]`).classList.add('active');
    document.getElementById(`${tab}-tab`).classList.add('active');
    
    // Initialize trading panel when switched to
    if (tab === 'trading') {
        initTradingPanel();
    }
};

// Listen for simulation mode changes
document.addEventListener('DOMContentLoaded', () => {
    const simToggle = document.getElementById('simulationMode');
    if (simToggle) {
        simToggle.addEventListener('change', () => {
            updateTradingModeDisplay();
            if (currentTab === 'trading') {
                loadTradingSymbols();
                refreshPositions();
                refreshAccountSummary();
            }
        });
    }
});


// ===== API Usage Functions =====

async function fetchUsage() {
    const authKey = document.getElementById('authKey').value;
    const simulationMode = document.getElementById('simulationMode').checked;
    
    if (!authKey) {
        showError('請輸入驗證金鑰');
        return;
    }
    
    try {
        const response = await fetch(`/usage?simulation=${simulationMode}`, {
            headers: { 'X-Auth-Key': authKey }
        });
        
        if (!response.ok) {
            throw new Error(response.status === 401 ? '驗證金鑰無效' : '載入失敗');
        }
        
        const data = await response.json();
        updateUsageDisplay(data);
        hideError();
        
    } catch (error) {
        showError(error.message);
    }
}

function updateUsageDisplay(data) {
    // Connections
    const connections = data.connections || 0;
    const maxConnections = 5;
    const connectionsPercent = (connections / maxConnections) * 100;
    
    document.getElementById('usageConnections').textContent = connections;
    document.getElementById('connectionsBar').style.width = `${connectionsPercent}%`;
    
    // Set bar color based on usage
    const connectionsBar = document.getElementById('connectionsBar');
    if (connectionsPercent >= 80) {
        connectionsBar.classList.add('danger');
        connectionsBar.classList.remove('warning');
    } else if (connectionsPercent >= 60) {
        connectionsBar.classList.add('warning');
        connectionsBar.classList.remove('danger');
    } else {
        connectionsBar.classList.remove('warning', 'danger');
    }
    
    // Bytes
    const bytes = data.bytes || 0;
    const limitBytes = data.limit_bytes || 1;
    const remainingBytes = data.remaining_bytes || 0;
    const bytesPercent = (bytes / limitBytes) * 100;
    const remainingPercent = (remainingBytes / limitBytes) * 100;
    
    document.getElementById('usageBytes').textContent = formatBytes(bytes);
    document.getElementById('usageLimitBytes').textContent = formatBytes(limitBytes);
    document.getElementById('usageRemainingBytes').textContent = formatBytes(remainingBytes);
    document.getElementById('usageRemainingPercent').textContent = remainingPercent.toFixed(1);
    document.getElementById('bytesBar').style.width = `${bytesPercent}%`;
    
    // Set bar color based on usage
    const bytesBar = document.getElementById('bytesBar');
    if (bytesPercent >= 80) {
        bytesBar.classList.add('danger');
        bytesBar.classList.remove('warning');
    } else if (bytesPercent >= 60) {
        bytesBar.classList.add('warning');
        bytesBar.classList.remove('danger');
    } else {
        bytesBar.classList.remove('warning', 'danger');
    }
}

function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Auto-fetch usage when switching to limits tab
const originalSwitchTabForLimits = switchTab;
switchTab = function(tab) {
    originalSwitchTabForLimits(tab);
    
    if (tab === 'limits') {
        fetchUsage();
    }
};

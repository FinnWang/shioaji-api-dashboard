/**
 * 即時報價圖表模組
 * 使用 Lightweight Charts (TradingView 開源圖表庫)
 *
 * 功能：
 * - 即時 K 線圖 / 分時圖
 * - 支撐壓力線顯示
 * - 交易點位標記（買入/賣出）
 */

// ============================================================================
// 設定
// ============================================================================

const CHART_CONFIG = {
    // shioaji-proxy API URL
    analysisApiUrl: 'https://tripple-f.zeabur.app',

    // 更新間隔（毫秒）
    updateInterval: 5000,

    // 圖表顏色
    colors: {
        background: '#1a1a2e',
        text: '#e4e4e7',
        grid: 'rgba(255, 255, 255, 0.1)',
        upColor: '#00ff88',
        downColor: '#ff6b6b',
        // 支撐壓力線顏色
        resistance: 'rgba(167, 139, 250, 0.7)',  // 紫色
        support: 'rgba(251, 146, 60, 0.7)',      // 橘色
        maxPain: 'rgba(255, 255, 255, 0.5)',     // 白色
        vwap: 'rgba(0, 217, 255, 0.7)',          // 藍色
        // 交易標記顏色
        buyMarker: '#00ff88',
        sellMarker: '#ff6b6b'
    }
};

// ============================================================================
// 狀態
// ============================================================================

let chart = null;
let candlestickSeries = null;
let volumeSeries = null;
let priceLines = [];
let tradeMarkers = [];
let chartUpdateTimer = null;
let currentChartSymbol = 'TXF';
let currentChartType = 'candlestick';  // 'candlestick' or 'area'
let showSupportResistance = true;
let analysisLevels = null;

// ============================================================================
// 初始化
// ============================================================================

/**
 * 初始化圖表
 */
function initRealtimeChart() {
    const container = document.getElementById('chartContainer');
    if (!container) {
        console.error('找不到圖表容器 #chartContainer');
        return;
    }

    // 建立圖表
    chart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 500,
        layout: {
            background: { type: 'solid', color: CHART_CONFIG.colors.background },
            textColor: CHART_CONFIG.colors.text,
        },
        grid: {
            vertLines: { color: CHART_CONFIG.colors.grid },
            horzLines: { color: CHART_CONFIG.colors.grid },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: CHART_CONFIG.colors.grid,
            scaleMargins: {
                top: 0.1,
                bottom: 0.2,
            },
        },
        timeScale: {
            borderColor: CHART_CONFIG.colors.grid,
            timeVisible: true,
            secondsVisible: false,
        },
        localization: {
            locale: 'zh-TW',
            dateFormat: 'yyyy-MM-dd',
        },
    });

    // 建立 K 線系列
    candlestickSeries = chart.addCandlestickSeries({
        upColor: CHART_CONFIG.colors.upColor,
        downColor: CHART_CONFIG.colors.downColor,
        borderUpColor: CHART_CONFIG.colors.upColor,
        borderDownColor: CHART_CONFIG.colors.downColor,
        wickUpColor: CHART_CONFIG.colors.upColor,
        wickDownColor: CHART_CONFIG.colors.downColor,
    });

    // 建立成交量系列
    volumeSeries = chart.addHistogramSeries({
        color: '#26a69a',
        priceFormat: {
            type: 'volume',
        },
        priceScaleId: '',
        scaleMargins: {
            top: 0.85,
            bottom: 0,
        },
    });

    // 監聽視窗大小變化
    window.addEventListener('resize', () => {
        if (chart && container) {
            chart.applyOptions({ width: container.clientWidth });
        }
    });

    // 載入數據
    loadChartData();
    loadAnalysisLevels();

    // 啟動自動更新
    startChartAutoUpdate();

    console.log('即時圖表初始化完成');
}

/**
 * 銷毀圖表
 */
function destroyRealtimeChart() {
    stopChartAutoUpdate();
    if (chart) {
        chart.remove();
        chart = null;
        candlestickSeries = null;
        volumeSeries = null;
    }
    priceLines = [];
    tradeMarkers = [];
}

// ============================================================================
// 數據載入
// ============================================================================

/**
 * 載入 K 線數據
 */
async function loadChartData() {
    const symbol = currentChartSymbol;
    const today = new Date().toISOString().split('T')[0];

    try {
        updateChartStatus('loading', '載入中...');

        const response = await fetch(
            `${CHART_CONFIG.analysisApiUrl}/api/kbars/${symbol}?start=${today}&end=${today}&session=day`
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();

        if (!result.success || !result.data || result.data.length === 0) {
            updateChartStatus('nodata', '無數據（非交易時段）');
            return;
        }

        // 轉換數據格式
        const candleData = result.data.map(kbar => ({
            time: parseTimestamp(kbar.ts),
            open: kbar.open,
            high: kbar.high,
            low: kbar.low,
            close: kbar.close,
        }));

        const volumeData = result.data.map(kbar => ({
            time: parseTimestamp(kbar.ts),
            value: kbar.volume,
            color: kbar.close >= kbar.open
                ? CHART_CONFIG.colors.upColor + '80'
                : CHART_CONFIG.colors.downColor + '80',
        }));

        // 設定數據
        candlestickSeries.setData(candleData);
        volumeSeries.setData(volumeData);

        // 調整視圖
        chart.timeScale().fitContent();

        updateChartStatus('connected', `${symbol} 即時`);

    } catch (error) {
        console.error('載入 K 線數據失敗:', error);
        updateChartStatus('error', '載入失敗');
    }
}

/**
 * 載入支撐壓力分析數據
 */
async function loadAnalysisLevels() {
    try {
        const response = await fetch(
            `${CHART_CONFIG.analysisApiUrl}/api/analysis/levels?symbol=${currentChartSymbol}`
        );

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const result = await response.json();

        if (!result.success || !result.data) {
            console.warn('無法取得支撐壓力數據');
            return;
        }

        analysisLevels = result.data;

        // 更新價格資訊顯示
        updatePriceInfo(result.data);

        // 繪製支撐壓力線
        if (showSupportResistance) {
            drawSupportResistanceLines(result.data);
        }

    } catch (error) {
        console.error('載入支撐壓力數據失敗:', error);
    }
}

/**
 * 更新價格資訊顯示
 */
function updatePriceInfo(data) {
    const quote = data.quote || {};
    const pivot = data.pivot_points || {};
    const oi = data.oi_levels || {};

    // 更新當前價格
    const priceEl = document.getElementById('chartCurrentPrice');
    if (priceEl && quote.close) {
        priceEl.textContent = quote.close.toLocaleString();
        priceEl.className = 'chart-price ' + (quote.change >= 0 ? 'up' : 'down');
    }

    // 更新漲跌
    const changeEl = document.getElementById('chartPriceChange');
    if (changeEl && quote.change !== undefined) {
        const sign = quote.change >= 0 ? '+' : '';
        changeEl.textContent = `${sign}${quote.change} (${sign}${quote.change_percent}%)`;
        changeEl.className = 'chart-change ' + (quote.change >= 0 ? 'up' : 'down');
    }

    // 更新支撐壓力摘要
    const levelsEl = document.getElementById('chartLevelsSummary');
    if (levelsEl) {
        let html = '';

        if (pivot.r1) {
            html += `<span class="level resistance">R1: ${pivot.r1.toLocaleString()}</span>`;
        }
        if (pivot.s1) {
            html += `<span class="level support">S1: ${pivot.s1.toLocaleString()}</span>`;
        }
        if (oi.max_pain) {
            html += `<span class="level maxpain">MP: ${oi.max_pain.toLocaleString()}</span>`;
        }

        levelsEl.innerHTML = html;
    }
}

/**
 * 繪製支撐壓力線
 */
function drawSupportResistanceLines(data) {
    // 清除舊的價格線
    priceLines.forEach(line => {
        try {
            candlestickSeries.removePriceLine(line);
        } catch (e) {}
    });
    priceLines = [];

    if (!candlestickSeries) return;

    const pivot = data.pivot_points || {};
    const oi = data.oi_levels || {};

    // Pivot Points 壓力線
    if (pivot.r1) {
        priceLines.push(candlestickSeries.createPriceLine({
            price: pivot.r1,
            color: CHART_CONFIG.colors.resistance,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: 'R1',
        }));
    }

    if (pivot.r2) {
        priceLines.push(candlestickSeries.createPriceLine({
            price: pivot.r2,
            color: CHART_CONFIG.colors.resistance,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dotted,
            axisLabelVisible: true,
            title: 'R2',
        }));
    }

    // Pivot Points 支撐線
    if (pivot.s1) {
        priceLines.push(candlestickSeries.createPriceLine({
            price: pivot.s1,
            color: CHART_CONFIG.colors.support,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: 'S1',
        }));
    }

    if (pivot.s2) {
        priceLines.push(candlestickSeries.createPriceLine({
            price: pivot.s2,
            color: CHART_CONFIG.colors.support,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dotted,
            axisLabelVisible: true,
            title: 'S2',
        }));
    }

    // Max Pain
    if (oi.max_pain) {
        priceLines.push(candlestickSeries.createPriceLine({
            price: oi.max_pain,
            color: CHART_CONFIG.colors.maxPain,
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: 'MP',
        }));
    }

    // OI 壓力
    if (oi.resistance && oi.resistance !== oi.max_pain) {
        priceLines.push(candlestickSeries.createPriceLine({
            price: oi.resistance,
            color: CHART_CONFIG.colors.resistance,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: 'OI壓',
        }));
    }

    // OI 支撐
    if (oi.support && oi.support !== oi.max_pain) {
        priceLines.push(candlestickSeries.createPriceLine({
            price: oi.support,
            color: CHART_CONFIG.colors.support,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: 'OI撐',
        }));
    }
}

// ============================================================================
// 交易標記
// ============================================================================

/**
 * 添加交易標記
 * @param {string} action - 'buy' or 'sell'
 * @param {number} price - 成交價格
 * @param {number} quantity - 成交數量
 * @param {Date|string} time - 成交時間
 */
function addTradeMarker(action, price, quantity, time) {
    if (!candlestickSeries) return;

    const timestamp = typeof time === 'string' ? parseTimestamp(time) : Math.floor(time.getTime() / 1000);

    const marker = {
        time: timestamp,
        position: action === 'buy' ? 'belowBar' : 'aboveBar',
        color: action === 'buy' ? CHART_CONFIG.colors.buyMarker : CHART_CONFIG.colors.sellMarker,
        shape: action === 'buy' ? 'arrowUp' : 'arrowDown',
        text: `${action === 'buy' ? '買' : '賣'} ${price} x${quantity}`,
    };

    tradeMarkers.push(marker);
    candlestickSeries.setMarkers(tradeMarkers);

    // 添加到交易記錄列表
    addTradeToList(action, price, quantity, time);

    console.log(`添加交易標記: ${action} @ ${price} x ${quantity}`);
}

/**
 * 清除所有交易標記
 */
function clearTradeMarkers() {
    tradeMarkers = [];
    if (candlestickSeries) {
        candlestickSeries.setMarkers([]);
    }

    // 清除交易記錄列表
    const listEl = document.getElementById('chartTradesList');
    if (listEl) {
        listEl.innerHTML = '<div class="no-trades">尚無交易記錄</div>';
    }
}

/**
 * 添加交易到記錄列表
 */
function addTradeToList(action, price, quantity, time) {
    const listEl = document.getElementById('chartTradesList');
    if (!listEl) return;

    // 移除 "尚無交易記錄" 提示
    const noTrades = listEl.querySelector('.no-trades');
    if (noTrades) {
        noTrades.remove();
    }

    const timeStr = typeof time === 'string' ? time : time.toLocaleTimeString('zh-TW');

    const tradeEl = document.createElement('div');
    tradeEl.className = `trade-item ${action}`;
    tradeEl.innerHTML = `
        <span class="trade-icon">${action === 'buy' ? '▲' : '▼'}</span>
        <span class="trade-action">${action === 'buy' ? '買入' : '賣出'}</span>
        <span class="trade-price">${price.toLocaleString()}</span>
        <span class="trade-qty">x${quantity}</span>
        <span class="trade-time">${timeStr}</span>
    `;

    listEl.insertBefore(tradeEl, listEl.firstChild);
}

// ============================================================================
// 自動更新
// ============================================================================

/**
 * 啟動自動更新
 */
function startChartAutoUpdate() {
    stopChartAutoUpdate();
    chartUpdateTimer = setInterval(() => {
        loadChartData();
        loadAnalysisLevels();
    }, CHART_CONFIG.updateInterval);
}

/**
 * 停止自動更新
 */
function stopChartAutoUpdate() {
    if (chartUpdateTimer) {
        clearInterval(chartUpdateTimer);
        chartUpdateTimer = null;
    }
}

/**
 * 手動刷新
 */
function refreshChart() {
    loadChartData();
    loadAnalysisLevels();
}

// ============================================================================
// UI 控制
// ============================================================================

/**
 * 切換商品
 */
function changeChartSymbol(symbol) {
    currentChartSymbol = symbol;
    clearTradeMarkers();
    loadChartData();
    loadAnalysisLevels();
}

/**
 * 切換支撐壓力線顯示
 */
function toggleSupportResistance() {
    showSupportResistance = !showSupportResistance;

    const btn = document.getElementById('toggleLevelsBtn');
    if (btn) {
        btn.textContent = showSupportResistance ? '隱藏支撐壓力' : '顯示支撐壓力';
        btn.classList.toggle('active', showSupportResistance);
    }

    if (showSupportResistance && analysisLevels) {
        drawSupportResistanceLines(analysisLevels);
    } else {
        // 清除價格線
        priceLines.forEach(line => {
            try {
                candlestickSeries.removePriceLine(line);
            } catch (e) {}
        });
        priceLines = [];
    }
}

/**
 * 更新圖表狀態
 */
function updateChartStatus(status, message) {
    const statusEl = document.getElementById('chartStatus');
    if (!statusEl) return;

    statusEl.className = 'chart-status ' + status;
    statusEl.innerHTML = `<span class="status-dot"></span>${message}`;
}

// ============================================================================
// 工具函數
// ============================================================================

/**
 * 解析時間戳
 */
function parseTimestamp(ts) {
    if (typeof ts === 'number') {
        return ts;
    }

    // 處理 "2026-02-06T09:00:00" 格式
    const date = new Date(ts);
    return Math.floor(date.getTime() / 1000);
}

// ============================================================================
// 與下單功能整合
// ============================================================================

/**
 * 當下單成功時調用此函數，在圖表上標記交易點位
 * 這個函數會被 dashboard.js 中的下單邏輯調用
 */
function onOrderFilled(orderData) {
    if (!orderData) return;

    const action = orderData.action?.includes('entry')
        ? (orderData.action.includes('long') ? 'buy' : 'sell')
        : (orderData.action.includes('long') ? 'sell' : 'buy');

    const price = orderData.fill_price || orderData.price || 0;
    const quantity = orderData.fill_quantity || orderData.quantity || 1;
    const time = orderData.filled_at || new Date();

    if (price > 0) {
        addTradeMarker(action, price, quantity, time);
    }
}

// 導出給全局使用
window.initRealtimeChart = initRealtimeChart;
window.destroyRealtimeChart = destroyRealtimeChart;
window.addTradeMarker = addTradeMarker;
window.clearTradeMarkers = clearTradeMarkers;
window.refreshChart = refreshChart;
window.changeChartSymbol = changeChartSymbol;
window.toggleSupportResistance = toggleSupportResistance;
window.onOrderFilled = onOrderFilled;

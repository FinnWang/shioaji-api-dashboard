/**
 * 本地即時分時圖表模組
 * 使用本地 WebSocket 連接，顯示即時 Tick 數據
 */

// ============================================================================
// 設定
// ============================================================================

const LOCAL_CHART_CONFIG = {
    // WebSocket URL (自動判斷 ws:// 或 wss://)
    wsUrl: `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/quotes`,

    // 圖表顏色
    colors: {
        background: '#1a1a2e',
        text: '#e4e4e7',
        grid: 'rgba(255, 255, 255, 0.1)',
        upColor: '#00ff88',
        downColor: '#ff6b6b',
        lineColor: '#00d9ff',
    },

    // 支撐壓力線顏色
    levelColors: {
        resistance: 'rgba(167, 139, 250, 0.7)',  // 紫色
        support: 'rgba(251, 146, 60, 0.7)',      // 橘色
        maxPain: 'rgba(255, 255, 255, 0.5)',     // 白色
        vwap: 'rgba(0, 217, 255, 0.7)',          // 藍色
    },

    // 支撐壓力更新間隔 (毫秒)
    levelsUpdateInterval: 60000,

    // 數據保留數量（最多顯示多少個 tick）
    maxDataPoints: 500,
};

// ============================================================================
// 狀態
// ============================================================================

let localChart = null;
let localLineSeries = null;
let localVolumeSeries = null;
let localWs = null;
let localChartData = [];
let localCurrentSymbol = 'TMFR1';
let localReconnectTimer = null;
let localReconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

// 支撐壓力線狀態
let localPriceLines = [];
let localAnalysisLevels = null;
let localLevelsUpdateTimer = null;

// VWAP 狀態
let localVwapData = { totalValue: 0, totalVolume: 0, vwap: 0 };
let localVwapLine = null;

// ============================================================================
// WebSocket 連線
// ============================================================================

/**
 * 建立 WebSocket 連線
 */
function connectLocalWebSocket() {
    if (localWs && localWs.readyState === WebSocket.OPEN) {
        console.log('[WS] 已連線，跳過重複連線');
        return;
    }

    updateLocalChartStatus('connecting', '連線中...');
    console.log(`[WS] 連線到: ${LOCAL_CHART_CONFIG.wsUrl}`);

    try {
        localWs = new WebSocket(LOCAL_CHART_CONFIG.wsUrl);

        localWs.onopen = () => {
            console.log('[WS] 連線成功');
            updateLocalChartStatus('connected', `${localCurrentSymbol} 即時`);
            localReconnectAttempts = 0;

            // 訂閱當前商品
            subscribeLocalSymbol(localCurrentSymbol);

            // 啟動心跳
            startLocalHeartbeat();
        };

        localWs.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                handleLocalWebSocketMessage(message);
            } catch (error) {
                console.error('[WS] 解析訊息失敗:', error);
            }
        };

        localWs.onerror = (error) => {
            console.error('[WS] 錯誤:', error);
            updateLocalChartStatus('error', '連線錯誤');
        };

        localWs.onclose = () => {
            console.log('[WS] 連線關閉');
            updateLocalChartStatus('disconnected', '已斷線');
            stopLocalHeartbeat();

            // 自動重連
            if (localReconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                localReconnectAttempts++;
                const delay = Math.min(1000 * Math.pow(2, localReconnectAttempts), 30000);
                console.log(`[WS] ${delay}ms 後重連 (第 ${localReconnectAttempts} 次)`);
                
                localReconnectTimer = setTimeout(() => {
                    connectLocalWebSocket();
                }, delay);
            } else {
                updateLocalChartStatus('error', '連線失敗（已達重試上限）');
            }
        };

    } catch (error) {
        console.error('[WS] 建立連線失敗:', error);
        updateLocalChartStatus('error', '無法建立連線');
    }
}

/**
 * 關閉 WebSocket 連線
 */
function disconnectLocalWebSocket() {
    stopLocalHeartbeat();

    if (localReconnectTimer) {
        clearTimeout(localReconnectTimer);
        localReconnectTimer = null;
    }

    if (localWs) {
        // 取消訂閱
        if (localWs.readyState === WebSocket.OPEN) {
            localWs.send(JSON.stringify({
                type: 'unsubscribe',
                symbol: localCurrentSymbol
            }));
        }

        localWs.close();
        localWs = null;
    }
}

/**
 * 訂閱商品報價
 */
function subscribeLocalSymbol(symbol) {
    if (!localWs || localWs.readyState !== WebSocket.OPEN) {
        console.warn('[WS] 未連線，無法訂閱');
        return;
    }

    console.log(`[WS] 訂閱: ${symbol}`);
    localWs.send(JSON.stringify({
        type: 'subscribe',
        symbol: symbol,
        simulation: true  // 使用模擬模式
    }));
}

/**
 * 取消訂閱商品報價
 */
function unsubscribeLocalSymbol(symbol) {
    if (!localWs || localWs.readyState !== WebSocket.OPEN) {
        return;
    }

    console.log(`[WS] 取消訂閱: ${symbol}`);
    localWs.send(JSON.stringify({
        type: 'unsubscribe',
        symbol: symbol
    }));
}

// ============================================================================
// 心跳機制
// ============================================================================

let localHeartbeatTimer = null;

function startLocalHeartbeat() {
    stopLocalHeartbeat();
    
    localHeartbeatTimer = setInterval(() => {
        if (localWs && localWs.readyState === WebSocket.OPEN) {
            localWs.send(JSON.stringify({ type: 'ping' }));
        }
    }, 30000); // 每 30 秒發送一次心跳
}

function stopLocalHeartbeat() {
    if (localHeartbeatTimer) {
        clearInterval(localHeartbeatTimer);
        localHeartbeatTimer = null;
    }
}

// ============================================================================
// 支撐壓力線
// ============================================================================

/**
 * 載入支撐壓力數據
 */
async function loadLocalAnalysisLevels() {
    try {
        // 根據商品代碼決定查詢的標的
        const symbol = localCurrentSymbol.startsWith('TMF') ? 'TXF' :
                       localCurrentSymbol.startsWith('MXF') ? 'MXF' : 'TXF';

        const response = await fetch(`/analysis/levels?symbol=${symbol}`);
        if (!response.ok) {
            console.warn('[Levels] API 回應錯誤:', response.status);
            return;
        }

        const result = await response.json();
        if (!result.success || !result.data) {
            console.warn('[Levels] 無有效數據');
            return;
        }

        localAnalysisLevels = result.data;
        drawLocalSupportResistanceLines(result.data);
        console.log('[Levels] 載入成功:', result.data);

    } catch (error) {
        console.error('[Levels] 載入失敗:', error);
    }
}

/**
 * 繪製支撐壓力線
 */
function drawLocalSupportResistanceLines(data) {
    clearLocalPriceLines();

    if (!localLineSeries) {
        return;
    }

    const pivot = data.pivot_points || {};
    const oi = data.oi_levels || {};

    // R1 壓力線 (紫色虛線)
    if (pivot.r1 > 0) {
        localPriceLines.push(localLineSeries.createPriceLine({
            price: pivot.r1,
            color: LOCAL_CHART_CONFIG.levelColors.resistance,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: 'R1',
        }));
    }

    // S1 支撐線 (橘色虛線)
    if (pivot.s1 > 0) {
        localPriceLines.push(localLineSeries.createPriceLine({
            price: pivot.s1,
            color: LOCAL_CHART_CONFIG.levelColors.support,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Dashed,
            axisLabelVisible: true,
            title: 'S1',
        }));
    }

    // Max Pain (白色實線，粗)
    if (oi.max_pain > 0) {
        localPriceLines.push(localLineSeries.createPriceLine({
            price: oi.max_pain,
            color: LOCAL_CHART_CONFIG.levelColors.maxPain,
            lineWidth: 2,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: 'MP',
        }));
    }

    // OI 壓力 (紫色實線)
    if (oi.resistance > 0 && oi.resistance !== oi.max_pain) {
        localPriceLines.push(localLineSeries.createPriceLine({
            price: oi.resistance,
            color: LOCAL_CHART_CONFIG.levelColors.resistance,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: 'OI壓',
        }));
    }

    // OI 支撐 (橘色實線)
    if (oi.support > 0 && oi.support !== oi.max_pain) {
        localPriceLines.push(localLineSeries.createPriceLine({
            price: oi.support,
            color: LOCAL_CHART_CONFIG.levelColors.support,
            lineWidth: 1,
            lineStyle: LightweightCharts.LineStyle.Solid,
            axisLabelVisible: true,
            title: 'OI撐',
        }));
    }
}

/**
 * 清除所有支撐壓力線
 */
function clearLocalPriceLines() {
    localPriceLines.forEach(line => {
        try {
            if (localLineSeries) {
                localLineSeries.removePriceLine(line);
            }
        } catch (e) {
            // 忽略移除失敗
        }
    });
    localPriceLines = [];
}

/**
 * 啟動支撐壓力線定時更新
 */
function startLocalLevelsAutoUpdate() {
    stopLocalLevelsAutoUpdate();
    localLevelsUpdateTimer = setInterval(() => {
        loadLocalAnalysisLevels();
    }, LOCAL_CHART_CONFIG.levelsUpdateInterval);
}

/**
 * 停止支撐壓力線定時更新
 */
function stopLocalLevelsAutoUpdate() {
    if (localLevelsUpdateTimer) {
        clearInterval(localLevelsUpdateTimer);
        localLevelsUpdateTimer = null;
    }
}

// ============================================================================
// VWAP 計算
// ============================================================================

/**
 * 更新 VWAP 線
 */
function updateLocalVwapLine(vwapPrice) {
    if (!localLineSeries || vwapPrice <= 0) {
        return;
    }

    // 移除舊的 VWAP 線
    if (localVwapLine) {
        try {
            localLineSeries.removePriceLine(localVwapLine);
        } catch (e) {
            // 忽略移除失敗
        }
    }

    // 建立新的 VWAP 線
    localVwapLine = localLineSeries.createPriceLine({
        price: vwapPrice,
        color: LOCAL_CHART_CONFIG.levelColors.vwap,
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Solid,
        axisLabelVisible: true,
        title: 'VWAP',
    });
}

/**
 * 重置 VWAP 數據
 */
function resetLocalVwap() {
    localVwapData = { totalValue: 0, totalVolume: 0, vwap: 0 };

    if (localVwapLine && localLineSeries) {
        try {
            localLineSeries.removePriceLine(localVwapLine);
        } catch (e) {
            // 忽略移除失敗
        }
        localVwapLine = null;
    }
}

// ============================================================================
// WebSocket 訊息處理
// ============================================================================

/**
 * 處理 WebSocket 訊息
 */
function handleLocalWebSocketMessage(message) {
    const { type, symbol, data } = message;

    switch (type) {
        case 'connected':
            console.log('[WS] 連線確認:', message);
            break;

        case 'subscribed':
            console.log('[WS] 訂閱成功:', symbol);
            updateLocalChartStatus('connected', `${symbol} 即時`);
            break;

        case 'unsubscribed':
            console.log('[WS] 取消訂閱:', symbol);
            break;

        case 'quote':
            // 處理報價更新
            if (symbol === localCurrentSymbol && data) {
                handleLocalQuoteUpdate(data);
            }
            break;

        case 'pong':
            // 心跳回應
            break;

        case 'error':
            console.error('[WS] 錯誤:', message.message);
            updateLocalChartStatus('error', message.message);
            break;

        default:
            console.warn('[WS] 未知訊息類型:', type);
    }
}

/**
 * 處理報價更新
 */
function handleLocalQuoteUpdate(quoteData) {
    if (!localLineSeries || !localVolumeSeries) {
        return;
    }

    // 解析報價數據
    const timestamp = quoteData.timestamp ? Math.floor(quoteData.timestamp / 1000) : Math.floor(Date.now() / 1000);
    const close = parseFloat(quoteData.close) || 0;
    const volume = parseInt(quoteData.volume) || 0;

    if (close === 0) {
        return; // 跳過無效數據
    }

    // 計算 VWAP
    if (close > 0 && volume > 0) {
        localVwapData.totalValue += close * volume;
        localVwapData.totalVolume += volume;
        localVwapData.vwap = localVwapData.totalValue / localVwapData.totalVolume;
        updateLocalVwapLine(localVwapData.vwap);
    }

    // 添加到數據陣列
    localChartData.push({
        time: timestamp,
        value: close,
        volume: volume
    });

    // 限制數據點數量
    if (localChartData.length > LOCAL_CHART_CONFIG.maxDataPoints) {
        localChartData.shift();
    }

    // 更新圖表
    try {
        localLineSeries.setData(localChartData.map(d => ({
            time: d.time,
            value: d.value
        })));

        localVolumeSeries.setData(localChartData.map(d => ({
            time: d.time,
            value: d.volume,
            color: LOCAL_CHART_CONFIG.colors.upColor + '80'
        })));

        // 更新價格顯示
        updateLocalPriceDisplay(quoteData);

    } catch (error) {
        console.error('[圖表] 更新失敗:', error);
    }
}

/**
 * 更新價格顯示
 */
function updateLocalPriceDisplay(quoteData) {
    const priceEl = document.getElementById('chartCurrentPrice');
    const changeEl = document.getElementById('chartPriceChange');

    if (priceEl && quoteData.close) {
        priceEl.textContent = parseFloat(quoteData.close).toLocaleString();
        priceEl.className = 'chart-price ' + (quoteData.change_price >= 0 ? 'up' : 'down');
    }

    if (changeEl && quoteData.change_price !== undefined) {
        const sign = quoteData.change_price >= 0 ? '+' : '';
        const changeRate = quoteData.change_rate || 0;
        changeEl.textContent = `${sign}${quoteData.change_price} (${sign}${changeRate.toFixed(2)}%)`;
        changeEl.className = 'chart-change ' + (quoteData.change_price >= 0 ? 'up' : 'down');
    }

    // 更新買賣價
    const buyPriceEl = document.getElementById('chartBuyPrice');
    const sellPriceEl = document.getElementById('chartSellPrice');

    if (buyPriceEl && quoteData.buy_price) {
        buyPriceEl.textContent = parseFloat(quoteData.buy_price).toLocaleString();
    }

    if (sellPriceEl && quoteData.sell_price) {
        sellPriceEl.textContent = parseFloat(quoteData.sell_price).toLocaleString();
    }
}

// ============================================================================
// 圖表初始化
// ============================================================================

/**
 * 初始化本地即時圖表
 */
function initLocalRealtimeChart() {
    const container = document.getElementById('chartContainer');
    if (!container) {
        console.error('找不到圖表容器 #chartContainer');
        return;
    }

    // 檢查 Lightweight Charts 是否載入
    if (typeof LightweightCharts === 'undefined') {
        console.error('Lightweight Charts 未載入');
        updateLocalChartStatus('error', 'CDN 載入失敗');
        return;
    }

    try {
        // 建立圖表
        localChart = LightweightCharts.createChart(container, {
            width: container.clientWidth,
            height: 500,
            layout: {
                background: { type: 'solid', color: LOCAL_CHART_CONFIG.colors.background },
                textColor: LOCAL_CHART_CONFIG.colors.text,
            },
            grid: {
                vertLines: { color: LOCAL_CHART_CONFIG.colors.grid },
                horzLines: { color: LOCAL_CHART_CONFIG.colors.grid },
            },
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: LOCAL_CHART_CONFIG.colors.grid,
                scaleMargins: {
                    top: 0.1,
                    bottom: 0.2,
                },
            },
            timeScale: {
                borderColor: LOCAL_CHART_CONFIG.colors.grid,
                timeVisible: true,
                secondsVisible: true,
            },
            localization: {
                locale: 'zh-TW',
                timeFormatter: (time) => {
                    const date = new Date(time * 1000);
                    return date.toLocaleTimeString('zh-TW');
                },
            },
        });

        // 建立分時線系列
        localLineSeries = localChart.addLineSeries({
            color: LOCAL_CHART_CONFIG.colors.lineColor,
            lineWidth: 2,
            crosshairMarkerVisible: true,
            crosshairMarkerRadius: 4,
        });

        // 建立成交量系列
        localVolumeSeries = localChart.addHistogramSeries({
            color: LOCAL_CHART_CONFIG.colors.upColor,
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
            if (localChart && container) {
                localChart.applyOptions({ width: container.clientWidth });
            }
        });

        console.log('本地即時圖表初始化完成');

        // 連接 WebSocket
        connectLocalWebSocket();

        // 載入支撐壓力數據並啟動定時更新
        loadLocalAnalysisLevels();
        startLocalLevelsAutoUpdate();

        // 重置 VWAP
        resetLocalVwap();

    } catch (error) {
        console.error('圖表初始化失敗:', error);
        updateLocalChartStatus('error', '初始化失敗: ' + error.message);
    }
}

/**
 * 銷毀本地即時圖表
 */
function destroyLocalRealtimeChart() {
    // 斷開 WebSocket
    disconnectLocalWebSocket();

    // 停止支撐壓力線定時更新
    stopLocalLevelsAutoUpdate();

    // 清除支撐壓力線
    clearLocalPriceLines();

    // 重置 VWAP
    resetLocalVwap();

    // 清理圖表
    if (localChart) {
        localChart.remove();
        localChart = null;
        localLineSeries = null;
        localVolumeSeries = null;
    }

    localChartData = [];
}

// ============================================================================
// UI 控制
// ============================================================================

/**
 * 切換商品
 */
function changeLocalChartSymbol(symbol) {
    if (symbol === localCurrentSymbol) {
        return;
    }

    // 取消訂閱舊商品
    unsubscribeLocalSymbol(localCurrentSymbol);

    // 更新當前商品
    localCurrentSymbol = symbol;

    // 清空數據
    localChartData = [];
    if (localLineSeries) {
        localLineSeries.setData([]);
    }
    if (localVolumeSeries) {
        localVolumeSeries.setData([]);
    }

    // 重置 VWAP (切換商品時需要重新計算)
    resetLocalVwap();

    // 重新載入支撐壓力數據
    loadLocalAnalysisLevels();

    // 訂閱新商品
    subscribeLocalSymbol(symbol);

    updateLocalChartStatus('connected', `${symbol} 即時`);
}

/**
 * 手動刷新連線
 */
function refreshLocalChart() {
    disconnectLocalWebSocket();
    localReconnectAttempts = 0;
    setTimeout(() => {
        connectLocalWebSocket();
    }, 500);
}

/**
 * 更新圖表狀態
 */
function updateLocalChartStatus(status, message) {
    const statusEl = document.getElementById('chartStatus');
    if (!statusEl) return;

    statusEl.className = 'chart-status ' + status;
    statusEl.innerHTML = `<span class="status-dot"></span>${message}`;
}

// ============================================================================
// 導出給全局使用
// ============================================================================

window.initLocalRealtimeChart = initLocalRealtimeChart;
window.destroyLocalRealtimeChart = destroyLocalRealtimeChart;
window.changeLocalChartSymbol = changeLocalChartSymbol;
window.refreshLocalChart = refreshLocalChart;

console.log('本地即時圖表模組已載入');

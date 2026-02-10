/**
 * 本地即時分時圖表模組
 * 頁面載入時先取得當日歷史分鐘資料，再搭配 WebSocket 即時更新
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
};

// ============================================================================
// 狀態
// ============================================================================

let localChart = null;
let localLineSeries = null;
let localVolumeSeries = null;
let localWs = null;
let localChartData = [];      // 分鐘 K 線資料 [{time, open, high, low, close, volume}]
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

// 歷史資料載入狀態
let localHistoryLoaded = false;

// ============================================================================
// 歷史資料載入
// ============================================================================

/**
 * 載入當日歷史分鐘資料
 */
async function loadIntradayHistory(symbol) {
    try {
        updateLocalChartStatus('loading', '載入歷史資料...');
        console.log(`[History] 載入 ${symbol} 當日分時資料...`);

        const response = await fetch(`/quotes/intraday/${symbol}`);
        if (!response.ok) {
            console.warn('[History] API 回應錯誤:', response.status);
            updateLocalChartStatus('connected', `${symbol} 即時 (無歷史資料)`);
            return;
        }

        const result = await response.json();
        if (!result.success || !result.data || result.data.length === 0) {
            console.log('[History] 無當日歷史資料');
            updateLocalChartStatus('connected', `${symbol} 即時 (無歷史資料)`);
            return;
        }

        // 重置 VWAP
        localVwapData = { totalValue: 0, totalVolume: 0, vwap: 0 };

        // 將 API 回傳的分鐘資料轉換為圖表資料格式
        localChartData = [];
        for (const bar of result.data) {
            if (!bar.time || bar.close === null) continue;

            const timestamp = Math.floor(new Date(bar.time).getTime() / 1000);

            localChartData.push({
                time: timestamp,
                open: bar.open,
                high: bar.high,
                low: bar.low,
                close: bar.close,
                volume: bar.volume || 0,
            });

            // 累計 VWAP（使用 close * volume 近似）
            if (bar.close > 0 && bar.volume > 0) {
                localVwapData.totalValue += bar.close * bar.volume;
                localVwapData.totalVolume += bar.volume;
            }
        }

        // 計算 VWAP
        if (localVwapData.totalVolume > 0) {
            localVwapData.vwap = localVwapData.totalValue / localVwapData.totalVolume;
            updateLocalVwapLine(localVwapData.vwap);
        }

        // 設定圖表資料
        if (localLineSeries && localChartData.length > 0) {
            localLineSeries.setData(localChartData.map(d => ({
                time: d.time,
                value: d.close
            })));

            localVolumeSeries.setData(localChartData.map(d => ({
                time: d.time,
                value: d.volume,
                color: LOCAL_CHART_CONFIG.colors.upColor + '80'
            })));

            // 自動調整可視範圍到完整數據
            localChart.timeScale().fitContent();
        }

        // 更新漲跌顯示（使用最後一筆資料）
        const lastBar = result.data[result.data.length - 1];
        if (lastBar) {
            updateLocalPriceDisplay({
                close: lastBar.close,
                change_price: lastBar.change_price,
                change_rate: lastBar.change_rate,
            });
        }

        localHistoryLoaded = true;
        console.log(`[History] 載入完成，共 ${localChartData.length} 筆分鐘資料`);
        updateLocalChartStatus('connected', `${symbol} 即時`);

    } catch (error) {
        console.error('[History] 載入失敗:', error);
        updateLocalChartStatus('connected', `${symbol} 即時 (歷史載入失敗)`);
    }
}

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
        // 所有台指相關商品（TMF/MXF/TXF）都使用 TXF 的支撐壓力數據
        const symbol = 'TXF';

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
 * 繪製支撐壓力線（完整版：Pivot Points + OI + Strength Levels）
 */
function drawLocalSupportResistanceLines(data) {
    clearLocalPriceLines();

    if (!localLineSeries) {
        return;
    }

    const pivot = data.pivot_points || {};
    const oi = data.oi_levels || {};
    const resistances = data.resistances || [];
    const supports = data.supports || [];
    const apiVwap = data.vwap || 0;

    // 已繪製的價位（避免重複畫線）
    const drawnPrices = new Set();

    function addPriceLine(price, color, lineWidth, lineStyle, title) {
        if (price <= 0 || drawnPrices.has(price)) return;
        drawnPrices.add(price);
        localPriceLines.push(localLineSeries.createPriceLine({
            price, color, lineWidth, lineStyle,
            axisLabelVisible: true,
            title,
        }));
    }

    // === Pivot Points ===
    // PP 軸心 (白色點線)
    if (pivot.pp > 0) {
        addPriceLine(pivot.pp, 'rgba(255, 255, 255, 0.4)', 1,
            LightweightCharts.LineStyle.Dotted, 'PP');
    }

    // R1 壓力 (紫色虛線)
    if (pivot.r1 > 0) {
        addPriceLine(pivot.r1, LOCAL_CHART_CONFIG.levelColors.resistance, 1,
            LightweightCharts.LineStyle.Dashed, 'R1');
    }

    // R2 壓力 (淡紫虛線)
    if (pivot.r2 > 0) {
        addPriceLine(pivot.r2, 'rgba(167, 139, 250, 0.4)', 1,
            LightweightCharts.LineStyle.Dotted, 'R2');
    }

    // R3 壓力 (更淡紫虛線)
    if (pivot.r3 > 0) {
        addPriceLine(pivot.r3, 'rgba(167, 139, 250, 0.25)', 1,
            LightweightCharts.LineStyle.Dotted, 'R3');
    }

    // S1 支撐 (橘色虛線)
    if (pivot.s1 > 0) {
        addPriceLine(pivot.s1, LOCAL_CHART_CONFIG.levelColors.support, 1,
            LightweightCharts.LineStyle.Dashed, 'S1');
    }

    // S2 支撐 (淡橘虛線)
    if (pivot.s2 > 0) {
        addPriceLine(pivot.s2, 'rgba(251, 146, 60, 0.4)', 1,
            LightweightCharts.LineStyle.Dotted, 'S2');
    }

    // S3 支撐 (更淡橘虛線)
    if (pivot.s3 > 0) {
        addPriceLine(pivot.s3, 'rgba(251, 146, 60, 0.25)', 1,
            LightweightCharts.LineStyle.Dotted, 'S3');
    }

    // === OI 支撐壓力 ===
    // Max Pain (黃色實線，粗)
    if (oi.max_pain > 0) {
        addPriceLine(oi.max_pain, 'rgba(250, 204, 21, 0.8)', 2,
            LightweightCharts.LineStyle.Solid, 'MP');
    }

    // OI 壓力 (紅紫實線)
    if (oi.resistance > 0) {
        addPriceLine(oi.resistance, 'rgba(239, 68, 68, 0.6)', 1,
            LightweightCharts.LineStyle.Solid, 'OI壓');
    }

    // OI 支撐 (綠色實線)
    if (oi.support > 0) {
        addPriceLine(oi.support, 'rgba(34, 197, 94, 0.6)', 1,
            LightweightCharts.LineStyle.Solid, 'OI撐');
    }

    // === API VWAP（若有值且本地 VWAP 尚未計算）===
    if (apiVwap > 0 && localVwapData.totalVolume === 0) {
        updateLocalVwapLine(apiVwap);
    }

    // === Strength Levels（綜合強度支撐壓力）===
    // 壓力線（按 strength 由高到低，取前 3 條避免太密）
    const topResistances = resistances
        .filter(r => r.price > 0)
        .sort((a, b) => b.strength - a.strength)
        .slice(0, 3);

    for (const r of topResistances) {
        const alpha = Math.min(0.3 + r.strength * 0.15, 0.9);
        addPriceLine(r.price, `rgba(239, 68, 68, ${alpha})`, 1,
            LightweightCharts.LineStyle.Dashed, r.label || '壓');
    }

    // 支撐線（按 strength 由高到低，取前 3 條）
    const topSupports = supports
        .filter(s => s.price > 0)
        .sort((a, b) => b.strength - a.strength)
        .slice(0, 3);

    for (const s of topSupports) {
        const alpha = Math.min(0.3 + s.strength * 0.15, 0.9);
        addPriceLine(s.price, `rgba(34, 197, 94, ${alpha})`, 1,
            LightweightCharts.LineStyle.Dashed, s.label || '撐');
    }

    console.log(`[Levels] 繪製完成: ${drawnPrices.size} 條線`);
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
 * 處理報價更新 - 將 tick 聚合到分鐘 K 線
 */
function handleLocalQuoteUpdate(quoteData) {
    if (!localLineSeries || !localVolumeSeries) {
        return;
    }

    // 解析報價數據
    const rawTimestamp = quoteData.timestamp ? Math.floor(quoteData.timestamp / 1000) : Math.floor(Date.now() / 1000);
    const close = parseFloat(quoteData.close) || 0;
    const volume = parseInt(quoteData.volume) || 0;

    if (close === 0) {
        return; // 跳過無效數據
    }

    // 將 timestamp 對齊到分鐘（取整到分鐘起始）
    const minuteTimestamp = rawTimestamp - (rawTimestamp % 60);

    // 計算 VWAP
    if (close > 0 && volume > 0) {
        localVwapData.totalValue += close * volume;
        localVwapData.totalVolume += volume;
        localVwapData.vwap = localVwapData.totalValue / localVwapData.totalVolume;
        updateLocalVwapLine(localVwapData.vwap);
    }

    // 檢查是否屬於已存在的分鐘
    const lastBar = localChartData.length > 0 ? localChartData[localChartData.length - 1] : null;

    if (lastBar && lastBar.time === minuteTimestamp) {
        // 同一分鐘：更新 high/low/close/volume
        lastBar.high = Math.max(lastBar.high, close);
        lastBar.low = Math.min(lastBar.low, close);
        lastBar.close = close;
        lastBar.volume += volume;
    } else {
        // 新分鐘：新增一筆分鐘資料
        localChartData.push({
            time: minuteTimestamp,
            open: close,
            high: close,
            low: close,
            close: close,
            volume: volume,
        });
    }

    // 更新圖表（使用 update 提升效能）
    try {
        const currentBar = localChartData[localChartData.length - 1];

        localLineSeries.update({
            time: currentBar.time,
            value: currentBar.close,
        });

        localVolumeSeries.update({
            time: currentBar.time,
            value: currentBar.volume,
            color: LOCAL_CHART_CONFIG.colors.upColor + '80',
        });

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
async function initLocalRealtimeChart() {
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
                secondsVisible: false,
            },
            localization: {
                locale: 'zh-TW',
                timeFormatter: (time) => {
                    const date = new Date(time * 1000);
                    return date.toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' });
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

        // 重置 VWAP
        resetLocalVwap();

        // 先載入當日歷史資料
        await loadIntradayHistory(localCurrentSymbol);

        // 歷史載入完成後再連接 WebSocket
        connectLocalWebSocket();

        // 載入支撐壓力數據並啟動定時更新
        loadLocalAnalysisLevels();
        startLocalLevelsAutoUpdate();

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
    localHistoryLoaded = false;
}

// ============================================================================
// UI 控制
// ============================================================================

/**
 * 切換商品
 */
async function changeLocalChartSymbol(symbol) {
    if (symbol === localCurrentSymbol) {
        return;
    }

    // 取消訂閱舊商品
    unsubscribeLocalSymbol(localCurrentSymbol);

    // 更新當前商品
    localCurrentSymbol = symbol;

    // 清空數據
    localChartData = [];
    localHistoryLoaded = false;
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

    // 載入新商品的歷史資料
    await loadIntradayHistory(symbol);

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

    // 重新載入歷史資料並重連
    localChartData = [];
    localHistoryLoaded = false;
    if (localLineSeries) {
        localLineSeries.setData([]);
    }
    if (localVolumeSeries) {
        localVolumeSeries.setData([]);
    }
    resetLocalVwap();

    loadIntradayHistory(localCurrentSymbol).then(() => {
        connectLocalWebSocket();
    });
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

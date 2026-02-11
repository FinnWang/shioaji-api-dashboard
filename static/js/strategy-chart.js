/**
 * strategy-chart.js - 策略即時圖表
 *
 * 使用 Lightweight Charts 建立策略專用 K 線圖表 + 損益曲線。
 * 提供 entry/exit/stop_loss 標記功能。
 */

// ==================== 策略 K 線圖表 ====================

let strategyChart = null;
let strategyCandleSeries = null;
let strategyMarkers = [];
let strategyKlineData = [];

// 損益曲線
let strategyPnlChart = null;
let strategyPnlSeries = null;
let strategyPnlData = [];
let strategyCumulativePnl = 0;

/**
 * 初始化策略 K 線圖表
 */
function initStrategyChart() {
    const container = document.getElementById('strategyChartContainer');
    if (!container || strategyChart) return;

    strategyChart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 400,
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#a1a1aa',
            fontSize: 12,
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal,
        },
        rightPriceScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
        },
        timeScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
            timeVisible: true,
            secondsVisible: false,
        },
    });

    strategyCandleSeries = strategyChart.addCandlestickSeries({
        upColor: '#00ff88',
        downColor: '#ff6b6b',
        borderUpColor: '#00ff88',
        borderDownColor: '#ff6b6b',
        wickUpColor: '#00ff88',
        wickDownColor: '#ff6b6b',
    });

    // 響應式調整
    const resizeObserver = new ResizeObserver(entries => {
        for (const entry of entries) {
            strategyChart.applyOptions({ width: entry.contentRect.width });
        }
    });
    resizeObserver.observe(container);

    // 載入當日 K 線
    loadStrategyIntradayData();
}

/**
 * 初始化損益曲線圖表
 */
function initStrategyPnlChart() {
    const container = document.getElementById('strategyPnlContainer');
    if (!container || strategyPnlChart) return;

    strategyPnlChart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 200,
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#a1a1aa',
            fontSize: 11,
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
        },
        rightPriceScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
        },
        timeScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
            timeVisible: true,
            secondsVisible: false,
        },
    });

    strategyPnlSeries = strategyPnlChart.addAreaSeries({
        lineColor: '#00d9ff',
        topColor: 'rgba(0, 217, 255, 0.2)',
        bottomColor: 'rgba(0, 217, 255, 0.0)',
        lineWidth: 2,
    });

    const resizeObserver = new ResizeObserver(entries => {
        for (const entry of entries) {
            strategyPnlChart.applyOptions({ width: entry.contentRect.width });
        }
    });
    resizeObserver.observe(container);
}

/**
 * 載入當日分時 K 線資料
 */
async function loadStrategyIntradayData() {
    try {
        const symbol = 'TMFR1'; // 預設商品
        const response = await fetch(`/quotes/intraday/${symbol}`);
        if (!response.ok) return;
        const result = await response.json();

        if (!result.success || !result.data || result.data.length === 0) return;

        strategyKlineData = result.data
            .filter(d => d.time && d.close != null)
            .map(d => ({
                time: Math.floor(new Date(d.time).getTime() / 1000),
                open: d.open ?? d.close,
                high: d.high ?? d.close,
                low: d.low ?? d.close,
                close: d.close,
            }));

        if (strategyCandleSeries && strategyKlineData.length > 0) {
            strategyCandleSeries.setData(strategyKlineData);
        }
    } catch (e) {
        console.error('載入策略 K 線失敗:', e);
    }
}

/**
 * 更新 K 線圖表（從 kline_complete 事件）
 */
function updateStrategyKline(data) {
    if (!strategyCandleSeries) return;

    try {
        const startTime = data.start_time;
        if (!startTime) return;

        const timestamp = Math.floor(new Date(startTime).getTime() / 1000);
        const kline = {
            time: timestamp,
            open: data.open,
            high: data.high,
            low: data.low,
            close: data.close,
        };

        strategyCandleSeries.update(kline);

        // 更新本地資料
        const existIdx = strategyKlineData.findIndex(k => k.time === timestamp);
        if (existIdx >= 0) {
            strategyKlineData[existIdx] = kline;
        } else {
            strategyKlineData.push(kline);
        }
    } catch (e) {
        console.error('更新策略 K 線失敗:', e);
    }
}

/**
 * 在 K 線圖表上加入交易標記
 */
function addStrategyMarker(eventType, data, timestampMs) {
    if (!strategyCandleSeries) return;

    const time = Math.floor(timestampMs / 1000);
    let marker = null;

    if (eventType === 'entry') {
        const isLong = data.direction === 'long';
        marker = {
            time: time,
            position: isLong ? 'belowBar' : 'aboveBar',
            color: isLong ? '#00ff88' : '#ff6b6b',
            shape: isLong ? 'arrowUp' : 'arrowDown',
            text: isLong ? `多 ${data.price}` : `空 ${data.price}`,
        };
    } else if (eventType === 'exit') {
        marker = {
            time: time,
            position: 'aboveBar',
            color: '#ffa726',
            shape: 'circle',
            text: `平 ${data.price} (${data.pnl > 0 ? '+' : ''}${data.pnl})`,
        };
    } else if (eventType === 'stop_loss') {
        marker = {
            time: time,
            position: 'aboveBar',
            color: '#ff1744',
            shape: 'circle',
            text: `停損 ${data.price}`,
        };
    }

    if (marker) {
        strategyMarkers.push(marker);
        // 按時間排序
        strategyMarkers.sort((a, b) => a.time - b.time);
        strategyCandleSeries.setMarkers(strategyMarkers);
    }
}

/**
 * 更新損益曲線（從 exit 事件）
 */
function updateStrategyPnlCurve(pnl, timestampMs) {
    if (!strategyPnlSeries) return;

    strategyCumulativePnl += pnl;
    const time = Math.floor(timestampMs / 1000);

    strategyPnlData.push({
        time: time,
        value: strategyCumulativePnl,
    });

    // 更新顏色
    if (strategyCumulativePnl >= 0) {
        strategyPnlSeries.applyOptions({
            lineColor: '#00ff88',
            topColor: 'rgba(0, 255, 136, 0.2)',
            bottomColor: 'rgba(0, 255, 136, 0.0)',
        });
    } else {
        strategyPnlSeries.applyOptions({
            lineColor: '#ff6b6b',
            topColor: 'rgba(255, 107, 107, 0.2)',
            bottomColor: 'rgba(255, 107, 107, 0.0)',
        });
    }

    strategyPnlSeries.setData(strategyPnlData);
}

/**
 * 銷毀策略圖表（分頁切換時清理）
 */
function destroyStrategyCharts() {
    // 不銷毀，只保持最新狀態
}

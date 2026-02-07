/**
 * 即時圖表備用方案
 * 當外部 API 無法使用時，使用模擬數據
 */

// 生成模擬 K 線數據
function generateMockKBarData(symbol, count = 100) {
    const data = [];
    const now = new Date();
    const basePrice = symbol === 'TXF' ? 18000 : symbol === 'MXF' ? 18000 : 18000;
    
    let currentPrice = basePrice;
    
    for (let i = count; i > 0; i--) {
        const time = new Date(now.getTime() - i * 60000); // 每分鐘一根 K 線
        const timestamp = Math.floor(time.getTime() / 1000);
        
        // 隨機波動
        const change = (Math.random() - 0.5) * 20;
        const open = currentPrice;
        const close = currentPrice + change;
        const high = Math.max(open, close) + Math.random() * 10;
        const low = Math.min(open, close) - Math.random() * 10;
        const volume = Math.floor(Math.random() * 1000) + 100;
        
        data.push({
            ts: timestamp,
            open: Math.round(open),
            high: Math.round(high),
            low: Math.round(low),
            close: Math.round(close),
            volume: volume
        });
        
        currentPrice = close;
    }
    
    return data;
}

// 生成模擬支撐壓力數據
function generateMockAnalysisLevels(symbol) {
    const basePrice = symbol === 'TXF' ? 18000 : symbol === 'MXF' ? 18000 : 18000;
    
    return {
        quote: {
            close: basePrice,
            change: Math.floor((Math.random() - 0.5) * 100),
            change_percent: ((Math.random() - 0.5) * 2).toFixed(2)
        },
        pivot_points: {
            r1: basePrice + 50,
            r2: basePrice + 100,
            s1: basePrice - 50,
            s2: basePrice - 100
        },
        oi_levels: {
            max_pain: basePrice,
            resistance: basePrice + 75,
            support: basePrice - 75
        }
    };
}

// 覆寫原有的載入函數，增加備用方案
const originalLoadChartData = window.loadChartData;
const originalLoadAnalysisLevels = window.loadAnalysisLevels;

// 備用的 K 線數據載入
async function loadChartDataWithFallback() {
    try {
        // 先嘗試原有的 API
        await originalLoadChartData();
    } catch (error) {
        console.warn('使用備用數據:', error);
        
        // 使用模擬數據
        const mockData = generateMockKBarData(currentChartSymbol);
        
        const candleData = mockData.map(kbar => ({
            time: kbar.ts,
            open: kbar.open,
            high: kbar.high,
            low: kbar.low,
            close: kbar.close,
        }));

        const volumeData = mockData.map(kbar => ({
            time: kbar.ts,
            value: kbar.volume,
            color: kbar.close >= kbar.open
                ? CHART_CONFIG.colors.upColor + '80'
                : CHART_CONFIG.colors.downColor + '80',
        }));

        candlestickSeries.setData(candleData);
        volumeSeries.setData(volumeData);
        chart.timeScale().fitContent();

        updateChartStatus('connected', `${currentChartSymbol} 模擬數據`);
    }
}

// 備用的支撐壓力數據載入
async function loadAnalysisLevelsWithFallback() {
    try {
        await originalLoadAnalysisLevels();
    } catch (error) {
        console.warn('使用備用分析數據:', error);
        
        const mockLevels = generateMockAnalysisLevels(currentChartSymbol);
        analysisLevels = mockLevels;
        
        updatePriceInfo(mockLevels);
        
        if (showSupportResistance) {
            drawSupportResistanceLines(mockLevels);
        }
    }
}

// 替換全局函數
if (typeof originalLoadChartData === 'function') {
    window.loadChartData = loadChartDataWithFallback;
}

if (typeof originalLoadAnalysisLevels === 'function') {
    window.loadAnalysisLevels = loadAnalysisLevelsWithFallback;
}

console.log('圖表備用方案已載入');

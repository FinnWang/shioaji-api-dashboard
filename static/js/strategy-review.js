/**
 * strategy-review.js - 策略復盤分頁邏輯
 *
 * 提供歷史交易查詢、績效分析、資金曲線、每日損益柱狀圖。
 */

let reviewEquityChart = null;
let reviewEquitySeries = null;
let reviewDailyPnlChart = null;
let reviewDailyPnlSeries = null;
let reviewInitialized = false;

/**
 * 初始化復盤分頁
 */
function initReviewTab() {
    if (!reviewInitialized) {
        // 設定預設日期為今日
        setReviewToday();
        reviewInitialized = true;

        // 延遲初始化圖表並自動載入今日資料
        setTimeout(() => {
            initReviewEquityChart();
            initReviewDailyPnlChart();
            loadReviewData();
        }, 150);
        return;
    }

    // 已初始化過，僅確保圖表存在
    setTimeout(() => {
        initReviewEquityChart();
        initReviewDailyPnlChart();
    }, 100);
}

/**
 * 設定日期快捷鍵：今日
 */
function setReviewToday() {
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('reviewStartDate').value = today;
    document.getElementById('reviewEndDate').value = today;
}

/**
 * 設定日期快捷鍵：本週
 */
function setReviewWeek() {
    const now = new Date();
    const dayOfWeek = now.getDay();
    const monday = new Date(now);
    monday.setDate(now.getDate() - (dayOfWeek === 0 ? 6 : dayOfWeek - 1));
    document.getElementById('reviewStartDate').value = monday.toISOString().split('T')[0];
    document.getElementById('reviewEndDate').value = now.toISOString().split('T')[0];
}

/**
 * 設定日期快捷鍵：本月
 */
function setReviewMonth() {
    const now = new Date();
    const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
    document.getElementById('reviewStartDate').value = firstDay.toISOString().split('T')[0];
    document.getElementById('reviewEndDate').value = now.toISOString().split('T')[0];
}

/**
 * 載入復盤資料
 */
async function loadReviewData() {
    const startDate = document.getElementById('reviewStartDate').value;
    const endDate = document.getElementById('reviewEndDate').value;

    if (!startDate || !endDate) {
        alert('請選擇日期範圍');
        return;
    }

    // 建立查詢參數（end_date 加一天以包含當日資料）
    const endDatePlusOne = new Date(endDate);
    endDatePlusOne.setDate(endDatePlusOne.getDate() + 1);
    const endDateStr = endDatePlusOne.toISOString().split('T')[0];

    const params = `start_date=${startDate}&end_date=${endDateStr}`;

    try {
        // 並行請求
        const [tradesRes, perfRes, dailyRes] = await Promise.all([
            fetch(`/strategy/trades?status=closed&${params}&limit=1000`),
            fetch(`/strategy/performance?${params}`),
            fetch(`/strategy/daily-summary?${params}`),
        ]);

        const trades = await tradesRes.json();
        const performance = await perfRes.json();
        const dailySummary = await dailyRes.json();

        // 更新各區域
        updateReviewPerformanceCards(performance);
        updateReviewTradeTable(trades);
        updateReviewEquityChart(trades);
        updateReviewDailyPnlChart(dailySummary);
    } catch (e) {
        console.error('載入復盤資料失敗:', e);
    }
}

/**
 * 更新績效摘要卡片
 */
function updateReviewPerformanceCards(perf) {
    const setEl = (id, text, className) => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = text;
            if (className) el.className = 'review-card-value ' + className;
        }
    };

    setEl('reviewTotalTrades', perf.total_trades || 0);
    setEl('reviewWinRate', perf.total_trades > 0 ? `${perf.win_rate}%` : '--');

    const totalPnl = perf.total_pnl || 0;
    const pnlSign = totalPnl >= 0 ? '+' : '';
    const pnlClass = totalPnl >= 0 ? 'pnl-positive' : 'pnl-negative';
    setEl('reviewTotalPnl', `${pnlSign}${totalPnl} 點`, pnlClass);

    const dd = perf.max_drawdown || 0;
    setEl('reviewMaxDrawdown', dd > 0 ? `-${dd} 點` : '0 點', dd > 0 ? 'pnl-negative' : '');

    const pf = perf.profit_factor;
    setEl('reviewProfitFactor', pf != null ? pf.toFixed(2) : '--');

    const sr = perf.sharpe_ratio || 0;
    setEl('reviewSharpeRatio', sr ? sr.toFixed(2) : '--');
}

/**
 * 更新交易列表
 */
function updateReviewTradeTable(trades) {
    const tbody = document.getElementById('reviewTradeTableBody');
    if (!tbody) return;

    if (!trades || trades.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="review-empty">此期間無交易記錄</td></tr>';
        return;
    }

    // 按進場時間排序（最新在上）
    const sorted = [...trades].sort((a, b) =>
        new Date(b.entry_time) - new Date(a.entry_time)
    );

    tbody.innerHTML = sorted.map(t => {
        const entryTime = t.entry_time ? new Date(t.entry_time).toLocaleString('zh-TW') : '--';
        const exitTime = t.exit_time ? new Date(t.exit_time).toLocaleString('zh-TW') : '--';
        const dirClass = t.direction === 'long' ? 'trade-long' : 'trade-short';
        const dirText = t.direction === 'long' ? '做多' : '做空';
        const pnl = t.pnl != null ? t.pnl : 0;
        const pnlClass = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
        const pnlSign = pnl >= 0 ? '+' : '';

        // 持倉時長
        let duration = '--';
        if (t.duration_seconds != null) {
            const mins = Math.floor(t.duration_seconds / 60);
            const secs = Math.floor(t.duration_seconds % 60);
            if (mins > 60) {
                const hours = Math.floor(mins / 60);
                const remMins = mins % 60;
                duration = `${hours}時${remMins}分`;
            } else {
                duration = `${mins}分${secs}秒`;
            }
        }

        // 出場原因
        const reasonMap = {
            signal: '策略訊號',
            fixed: '固定停損',
            trailing: '追蹤停損',
            daily: '每日停損',
            stop_loss: '停損',
        };
        const reason = reasonMap[t.exit_reason] || t.exit_reason || '--';

        return `<tr>
            <td>${entryTime}</td>
            <td>${exitTime}</td>
            <td><span class="${dirClass}">${dirText}</span></td>
            <td>${t.entry_price || '--'}</td>
            <td>${t.exit_price || '--'}</td>
            <td class="${pnlClass}">${pnlSign}${pnl} 點</td>
            <td>${duration}</td>
            <td>${reason}</td>
        </tr>`;
    }).join('');
}

/**
 * 初始化資金曲線圖表
 */
function initReviewEquityChart() {
    const container = document.getElementById('reviewEquityContainer');
    if (!container || reviewEquityChart) return;

    reviewEquityChart = LightweightCharts.createChart(container, {
        width: container.clientWidth,
        height: 300,
        layout: {
            background: { type: 'solid', color: 'transparent' },
            textColor: '#a1a1aa',
            fontSize: 12,
        },
        grid: {
            vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
            horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
        },
        rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.1)' },
        timeScale: {
            borderColor: 'rgba(255, 255, 255, 0.1)',
            timeVisible: true,
        },
    });

    reviewEquitySeries = reviewEquityChart.addAreaSeries({
        lineColor: '#00d9ff',
        topColor: 'rgba(0, 217, 255, 0.2)',
        bottomColor: 'rgba(0, 217, 255, 0.0)',
        lineWidth: 2,
    });

    const resizeObserver = new ResizeObserver(entries => {
        for (const entry of entries) {
            reviewEquityChart.applyOptions({ width: entry.contentRect.width });
        }
    });
    resizeObserver.observe(container);
}

/**
 * 初始化每日損益柱狀圖
 */
function initReviewDailyPnlChart() {
    const container = document.getElementById('reviewDailyPnlContainer');
    if (!container || reviewDailyPnlChart) return;

    reviewDailyPnlChart = LightweightCharts.createChart(container, {
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
        rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.1)' },
        timeScale: { borderColor: 'rgba(255, 255, 255, 0.1)' },
    });

    reviewDailyPnlSeries = reviewDailyPnlChart.addHistogramSeries({
        color: '#00ff88',
    });

    const resizeObserver = new ResizeObserver(entries => {
        for (const entry of entries) {
            reviewDailyPnlChart.applyOptions({ width: entry.contentRect.width });
        }
    });
    resizeObserver.observe(container);
}

/**
 * 更新資金曲線
 */
function updateReviewEquityChart(trades) {
    if (!reviewEquitySeries) return;

    if (!trades || trades.length === 0) {
        reviewEquitySeries.setData([]);
        return;
    }

    // 按進場時間排序
    const sorted = [...trades].sort((a, b) =>
        new Date(a.entry_time) - new Date(b.entry_time)
    );

    let cumPnl = 0;
    const data = sorted
        .filter(t => t.exit_time && t.pnl != null)
        .map(t => {
            cumPnl += t.pnl;
            return {
                time: Math.floor(new Date(t.exit_time).getTime() / 1000),
                value: cumPnl,
            };
        });

    if (data.length > 0) {
        // 根據最終損益決定顏色
        const finalPnl = data[data.length - 1].value;
        if (finalPnl >= 0) {
            reviewEquitySeries.applyOptions({
                lineColor: '#00ff88',
                topColor: 'rgba(0, 255, 136, 0.2)',
                bottomColor: 'rgba(0, 255, 136, 0.0)',
            });
        } else {
            reviewEquitySeries.applyOptions({
                lineColor: '#ff6b6b',
                topColor: 'rgba(255, 107, 107, 0.2)',
                bottomColor: 'rgba(255, 107, 107, 0.0)',
            });
        }
        reviewEquitySeries.setData(data);
        reviewEquityChart.timeScale().fitContent();
    } else {
        reviewEquitySeries.setData([]);
    }
}

/**
 * 更新每日損益柱狀圖
 */
function updateReviewDailyPnlChart(dailySummary) {
    if (!reviewDailyPnlSeries) return;

    if (!dailySummary || dailySummary.length === 0) {
        reviewDailyPnlSeries.setData([]);
        return;
    }

    const data = dailySummary.map(d => ({
        time: d.date,
        value: d.total_pnl,
        color: d.total_pnl >= 0 ? '#00ff88' : '#ff6b6b',
    }));

    reviewDailyPnlSeries.setData(data);
    reviewDailyPnlChart.timeScale().fitContent();
}

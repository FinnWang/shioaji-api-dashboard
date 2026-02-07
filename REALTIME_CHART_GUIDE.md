# 即時分時圖表使用指南

## 概述

本系統提供**本地 WebSocket 即時分時圖表**，直接連接到你的 Shioaji Trading Worker，顯示即時 Tick 數據。

## 架構說明

```
前端 (dashboard.html)
    ↓ WebSocket 連線
FastAPI (/ws/quotes)
    ↓ Redis Pub/Sub
Trading Worker
    ↓ Shioaji API
永豐金證券
```

### 數據流程

1. **前端訂閱** - 瀏覽器透過 WebSocket 連接到 `/ws/quotes`
2. **Trading Worker 訂閱** - FastAPI 透過 Redis Queue 請求 Trading Worker 訂閱 Shioaji 報價
3. **Shioaji 回調** - Trading Worker 收到 Shioaji 的 `on_tick_fop_v1` 回調
4. **Redis 發布** - Trading Worker 將報價發布到 Redis Pub/Sub
5. **WebSocket 推送** - FastAPI 監聽 Redis，將報價推送給前端
6. **圖表更新** - 前端收到報價後更新 Lightweight Charts

## 功能特點

✅ **即時分時圖** - 顯示每筆成交的 Tick 數據
✅ **自動訂閱** - 切換商品時自動訂閱/取消訂閱
✅ **自動重連** - 連線中斷時自動重連（最多 5 次）
✅ **心跳機制** - 每 30 秒發送心跳保持連線
✅ **數據限制** - 最多保留 500 個數據點，避免記憶體溢出

## 使用方式

### 1. 確認服務運行

確保以下服務正在運行：

```bash
# 檢查 Redis
redis-cli ping
# 應該回應: PONG

# 檢查 Trading Worker
# 查看 logs 確認 Worker 已啟動並登入成功

# 檢查 FastAPI
# 訪問 http://localhost:8000/ws/stats
# 應該回應: {"available": true, ...}
```

### 2. 開啟圖表

1. 訪問 Dashboard: `http://localhost:8000/static/dashboard.html`
2. 點擊「📈 即時圖表」分頁
3. 圖表會自動初始化並連接 WebSocket

### 3. 切換商品

使用下拉選單切換商品：
- **TMFR1** - 微型台指近月（預設）
- **MXFR1** - 小型台指近月
- **TXFR1** - 台指期近月

切換時會自動：
1. 取消訂閱舊商品
2. 清空圖表數據
3. 訂閱新商品

### 4. 查看即時報價

圖表上方顯示：
- **現價** - 最新成交價
- **漲跌** - 漲跌點數和百分比
- **買價** - 最佳買進價
- **賣價** - 最佳賣出價

## 連線狀態

圖表右上角顯示連線狀態：

| 狀態 | 說明 |
|------|------|
| 🟡 連線中... | 正在建立 WebSocket 連線 |
| 🟢 TMFR1 即時 | 已連線並訂閱成功 |
| 🔴 已斷線 | WebSocket 連線中斷 |
| 🔴 連線錯誤 | 連線失敗 |

## 故障排除

### 問題 1: 顯示「連線錯誤」

**可能原因：**
- FastAPI 服務未啟動
- WebSocket 端點無法訪問

**解決方案：**
```bash
# 檢查 FastAPI 是否運行
curl http://localhost:8000/ws/stats

# 重啟 FastAPI
python main.py
```

### 問題 2: 顯示「訂閱失敗」

**可能原因：**
- Trading Worker 未運行
- Trading Worker 未登入 Shioaji
- 商品代碼不存在

**解決方案：**
```bash
# 檢查 Trading Worker 日誌
# 確認看到類似訊息：
# [INFO] Shioaji 登入成功
# [INFO] QuoteManager 初始化完成

# 檢查商品是否存在
curl "http://localhost:8000/symbols/TMFR1"
```

### 問題 3: 無數據更新

**可能原因：**
- 非交易時段
- Shioaji 訂閱失敗
- Redis 連線問題

**解決方案：**

1. **確認交易時段**
   - 日盤: 08:45 - 13:45
   - 夜盤: 15:00 - 05:00 (次日)
   - 週末及國定假日休市

2. **檢查 Trading Worker 日誌**
   ```
   # 應該看到類似訊息：
   [INFO] [訂閱] 呼叫 Shioaji API: symbol=TMFR1
   [INFO] 已訂閱商品 TMFR1
   [INFO] [on_tick_fop_v1] 收到 Tick: code=TMFB6, close=31493.0
   ```

3. **檢查 Redis**
   ```bash
   # 監聽 Redis Pub/Sub
   redis-cli
   > PSUBSCRIBE quote:*
   
   # 應該看到報價訊息
   ```

### 問題 4: 圖表空白

**可能原因：**
- Lightweight Charts CDN 載入失敗
- JavaScript 錯誤

**解決方案：**
1. 按 F12 開啟開發者工具
2. 查看 Console 分頁的錯誤訊息
3. 查看 Network 分頁確認 CDN 載入成功
4. 清除瀏覽器快取 (Ctrl + Shift + Delete)

## WebSocket 訊息格式

### 客戶端 → 伺服器

**訂閱商品**
```json
{
  "type": "subscribe",
  "symbol": "TMFR1",
  "simulation": true
}
```

**取消訂閱**
```json
{
  "type": "unsubscribe",
  "symbol": "TMFR1"
}
```

**心跳**
```json
{
  "type": "ping"
}
```

### 伺服器 → 客戶端

**連線確認**
```json
{
  "type": "connected",
  "client_id": "uuid",
  "message": "WebSocket 連線成功"
}
```

**訂閱成功**
```json
{
  "type": "subscribed",
  "symbol": "TMFR1",
  "data": {
    "symbol": "TMFR1",
    "code": "TMFB6",
    "subscribed": true
  }
}
```

**報價更新**
```json
{
  "type": "quote",
  "symbol": "TMFR1",
  "data": {
    "symbol": "TMFR1",
    "code": "TMFB6",
    "close": 31493.0,
    "open": 31458.0,
    "high": 31500.0,
    "low": 31450.0,
    "change_price": 35.0,
    "change_rate": 0.11,
    "volume": 1,
    "total_volume": 12345,
    "buy_price": 31492.0,
    "sell_price": 31493.0,
    "timestamp": 1738819200000
  }
}
```

**心跳回應**
```json
{
  "type": "pong"
}
```

**錯誤訊息**
```json
{
  "type": "error",
  "message": "訂閱失敗: 商品不存在"
}
```

## 效能考量

### 數據點限制

圖表最多保留 **500 個數據點**，超過時會自動移除最舊的數據。

這是為了：
- 避免記憶體溢出
- 保持圖表渲染效能
- 適合日內交易的時間範圍

### 訂閱限制

根據 Shioaji API 限制：
- 每個帳號最多 **200 個訂閱**
- 多個客戶端訂閱同一商品時，Trading Worker 只會訂閱一次
- 當最後一個客戶端取消訂閱時，才會取消 Shioaji 訂閱

### 網路流量

- WebSocket 使用二進制或 JSON 格式，流量較小
- 每筆 Tick 約 200-300 bytes
- 活躍時段每秒可能有數十筆 Tick

## 開發者資訊

### 檔案結構

```
static/
├── js/
│   ├── realtime-chart-local.js  # 本地 WebSocket 圖表
│   └── dashboard.js             # Dashboard 主程式
├── css/
│   └── dashboard.css            # 樣式表
└── dashboard.html               # 主頁面

main.py                          # FastAPI WebSocket 端點
websocket_manager.py             # WebSocket 連線管理
quote_manager.py                 # 報價訂閱管理
trading_worker.py                # Trading Worker
```

### 關鍵函數

**前端 (realtime-chart-local.js)**
- `initLocalRealtimeChart()` - 初始化圖表
- `connectLocalWebSocket()` - 建立 WebSocket 連線
- `handleLocalQuoteUpdate()` - 處理報價更新
- `changeLocalChartSymbol()` - 切換商品

**後端 (main.py)**
- `websocket_quotes_endpoint()` - WebSocket 端點
- `ws_manager.subscribe_symbol()` - 訂閱商品
- `queue_client.subscribe_quote()` - 請求 Trading Worker 訂閱

**Trading Worker (quote_manager.py)**
- `subscribe()` - 訂閱 Shioaji 報價
- `_handle_tick_fop()` - 處理 Tick 回調
- `_redis.publish()` - 發布報價到 Redis

## 進階功能

### 自訂數據點數量

修改 `static/js/realtime-chart-local.js`:

```javascript
const LOCAL_CHART_CONFIG = {
    maxDataPoints: 1000,  // 改為 1000 個數據點
    // ...
};
```

### 自訂圖表顏色

修改 `static/js/realtime-chart-local.js`:

```javascript
const LOCAL_CHART_CONFIG = {
    colors: {
        lineColor: '#ff0000',  // 改為紅色
        // ...
    },
};
```

### 新增技術指標

可以使用 Lightweight Charts 的 API 新增移動平均線等指標：

```javascript
// 在 initLocalRealtimeChart() 中新增
const maSeries = localChart.addLineSeries({
    color: '#ffc107',
    lineWidth: 1,
});
```

## 相關文件

- [Shioaji API 文件](https://sinotrade.github.io/)
- [Lightweight Charts 文件](https://tradingview.github.io/lightweight-charts/)
- [FastAPI WebSocket 文件](https://fastapi.tiangolo.com/advanced/websockets/)
- [Redis Pub/Sub 文件](https://redis.io/docs/manual/pubsub/)

## 支援

如有問題，請檢查：
1. Trading Worker 日誌
2. FastAPI 日誌
3. 瀏覽器開發者工具 Console
4. Redis 連線狀態

或參考 `CHART_TROUBLESHOOTING.md` 進行故障排除。

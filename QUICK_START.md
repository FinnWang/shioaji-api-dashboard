# 即時圖表快速啟動指南

## 問題已解決 ✅

你的即時圖表現在使用**本地 WebSocket**，不再依賴外部 API。

## 啟動步驟

### 1. 啟動 Redis（如果尚未啟動）

```bash
# Windows
redis-server

# 或使用 Docker
docker run -d -p 6379:6379 redis
```

### 2. 啟動 Trading Worker

```bash
python trading_worker.py
```

等待看到：
```
[INFO] Shioaji 登入成功
[INFO] QuoteManager 初始化完成
```

### 3. 啟動 FastAPI

```bash
python main.py
```

等待看到：
```
INFO:     Uvicorn running on http://0.0.0.0:8000
[INFO] WebSocket Pub/Sub 監聽已啟動
```

### 4. 開啟圖表

1. 瀏覽器訪問: `http://localhost:8000/static/dashboard.html`
2. 點擊「📈 即時圖表」分頁
3. 等待連線（右上角應顯示「🟢 TMFR1 即時」）

## 驗證連線

### 方法 1: 使用測試腳本

```bash
python test_websocket_chart.py
```

預期輸出：
```
✅ WebSocket 連線成功
✅ 訂閱成功: TMFR1
📈 報價更新 #1: ...
```

### 方法 2: 檢查 WebSocket 狀態

```bash
curl http://localhost:8000/ws/stats
```

預期輸出：
```json
{
  "available": true,
  "connection_count": 0,
  "subscribed_symbols": []
}
```

### 方法 3: 瀏覽器開發者工具

1. 按 F12 開啟開發者工具
2. 切換到 Console 分頁
3. 應該看到：
   ```
   [WS] 連線成功
   [WS] 訂閱: TMFR1
   [WS] 訂閱成功: TMFR1
   ```

## 常見問題

### Q: 顯示「連線中...」不變？

**A:** FastAPI 未啟動或 WebSocket 端點無法訪問

```bash
# 檢查
curl http://localhost:8000/ws/stats

# 解決
python main.py
```

### Q: 顯示「訂閱失敗」？

**A:** Trading Worker 未運行或未登入

```bash
# 檢查 Trading Worker 日誌
# 應該看到: [INFO] Shioaji 登入成功

# 解決
python trading_worker.py
```

### Q: 無報價更新？

**A:** 可能是非交易時段

**交易時段：**
- 日盤: 08:45 - 13:45
- 夜盤: 15:00 - 05:00 (次日)
- 週末及國定假日休市

**檢查 Trading Worker 日誌：**
```
[INFO] [on_tick_fop_v1] 收到 Tick: code=TMFB6, close=31493.0
```

如果看到這個訊息，表示有收到報價。

## 檔案變更總結

### 新增檔案
- ✅ `static/js/realtime-chart-local.js` - 本地 WebSocket 圖表
- ✅ `test_websocket_chart.py` - 測試腳本
- ✅ `REALTIME_CHART_GUIDE.md` - 完整指南
- ✅ `CHART_SOLUTION_SUMMARY.md` - 解決方案總結
- ✅ `QUICK_START.md` - 本檔案

### 修改檔案
- ✅ `static/dashboard.html` - 更新 script 引用和 HTML
- ✅ `static/js/dashboard.js` - 更新函數名稱
- ✅ `static/css/dashboard.css` - 新增樣式

### 無需修改（已存在）
- ✅ `main.py` - WebSocket 端點
- ✅ `websocket_manager.py` - 連線管理
- ✅ `quote_manager.py` - 報價管理
- ✅ `trading_worker.py` - Trading Worker

## 清除瀏覽器快取

**重要！** 修改後務必清除快取：

```
Windows: Ctrl + Shift + Delete
Mac: Cmd + Shift + Delete

或強制重新載入:
Windows: Ctrl + F5
Mac: Cmd + Shift + R
```

## 下一步

圖表啟動後，你可以：

1. **切換商品** - 使用下拉選單切換 TMFR1/MXFR1/TXFR1
2. **查看即時報價** - 觀察價格、買賣價即時更新
3. **監控連線狀態** - 右上角顯示連線狀態
4. **刷新連線** - 點擊「🔄 刷新連線」按鈕

## 需要幫助？

查看詳細文件：
- `REALTIME_CHART_GUIDE.md` - 完整使用指南
- `CHART_TROUBLESHOOTING.md` - 故障排除
- `CHART_SOLUTION_SUMMARY.md` - 技術細節

或檢查日誌：
- Trading Worker 日誌
- FastAPI 日誌（終端輸出）
- 瀏覽器 Console（F12）

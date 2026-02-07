# 即時圖表故障排除指南

## 問題現象
即時圖表分頁無法載入或顯示錯誤訊息

## 可能原因與解決方案

### 1️⃣ Lightweight Charts CDN 載入失敗

**症狀：**
- 控制台顯示 `LightweightCharts is not defined`
- 圖表區域空白

**解決方案：**
```bash
# 方案 A: 檢查網路連線
ping unpkg.com

# 方案 B: 使用備用 CDN（修改 dashboard.html）
# 將 CDN 網址改為：
https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js
```

### 2️⃣ 外部 API 無法連線

**症狀：**
- 圖表狀態顯示「API 無法連線」
- 控制台顯示 `Failed to fetch`

**原因：**
- `https://tripple-f.zeabur.app` 服務離線或無法訪問
- 防火牆阻擋外部 API 請求
- CORS 政策限制

**解決方案：**

#### 選項 1: 使用診斷工具
```bash
# 開啟診斷頁面
http://localhost:8000/static/chart-debug.html
```

#### 選項 2: 檢查 API 狀態
```bash
# Windows PowerShell
Invoke-WebRequest -Uri "https://tripple-f.zeabur.app/health" -Method GET

# 或使用瀏覽器直接訪問
https://tripple-f.zeabur.app/health
```

#### 選項 3: 修改為本地 API
如果外部 API 不可用，可以修改 `static/js/realtime-chart.js`：

```javascript
const CHART_CONFIG = {
    // 改為本地 API（需要自行實作）
    analysisApiUrl: 'http://localhost:8000',
    // ...
};
```

### 3️⃣ 非交易時段無數據

**症狀：**
- 圖表狀態顯示「無數據（非交易時段或週末）」

**說明：**
這是正常現象，台灣期貨市場交易時間：
- 日盤：08:45 - 13:45
- 夜盤：15:00 - 05:00（次日）
- 週末及國定假日休市

**解決方案：**
等待交易時段再測試，或使用歷史數據測試

### 4️⃣ 瀏覽器快取問題

**症狀：**
- 修改程式碼後沒有生效
- 仍然看到舊版本的錯誤

**解決方案：**
```bash
# 清除瀏覽器快取
Ctrl + Shift + Delete (Windows)
Cmd + Shift + Delete (Mac)

# 或強制重新載入
Ctrl + F5 (Windows)
Cmd + Shift + R (Mac)
```

## 診斷步驟

### Step 1: 開啟診斷工具
訪問 `http://localhost:8000/static/chart-debug.html`

### Step 2: 檢查控制台
按 F12 開啟開發者工具，查看 Console 分頁的錯誤訊息

### Step 3: 檢查網路請求
在開發者工具的 Network 分頁，查看：
- `lightweight-charts.standalone.production.js` 是否成功載入（狀態 200）
- API 請求是否成功（`/api/kbars/...`）

### Step 4: 測試 API 連線
```bash
# 測試 K線 API
curl "https://tripple-f.zeabur.app/api/kbars/TXF?start=2026-02-06&end=2026-02-06&session=day"

# 測試支撐壓力 API
curl "https://tripple-f.zeabur.app/api/analysis/levels?symbol=TXF"
```

## 已修復的問題

✅ 增加 CDN 載入檢查
✅ 增加 API 請求超時處理（10秒）
✅ 改善錯誤訊息顯示
✅ 增加連線狀態提示

## 常見錯誤訊息

| 錯誤訊息 | 原因 | 解決方案 |
|---------|------|---------|
| `CDN 載入失敗` | Lightweight Charts 未載入 | 檢查網路或使用備用 CDN |
| `API 無法連線` | 外部 API 無法訪問 | 檢查網路或使用本地 API |
| `連線超時` | API 回應時間過長 | 檢查網路速度或 API 狀態 |
| `無數據（非交易時段）` | 市場休市 | 等待交易時段 |
| `初始化失敗` | 圖表建立錯誤 | 查看控制台詳細錯誤 |

## 聯絡支援

如果以上方法都無法解決問題，請提供：
1. 瀏覽器控制台的完整錯誤訊息
2. 診斷工具的檢測結果截圖
3. 網路環境資訊（是否使用代理、防火牆等）

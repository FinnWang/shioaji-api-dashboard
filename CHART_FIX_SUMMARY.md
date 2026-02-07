# 即時圖表修復總結

## 診斷結果

✅ **API 連線測試通過**
- API 健康檢查: 正常
- K 線數據 API: 正常 (取得 300 筆數據)
- 支撐壓力 API: 正常

這表示後端 API 服務運作正常，問題可能出在前端。

## 已實施的修復

### 1. 增強錯誤處理 ✅

**檔案:** `static/js/realtime-chart.js`

- ✅ 增加 CDN 載入檢查
- ✅ 增加 API 請求超時處理（10秒）
- ✅ 改善錯誤訊息顯示
- ✅ 增加 try-catch 錯誤捕獲

### 2. 建立診斷工具 ✅

**檔案:** `static/chart-debug.html`

提供完整的診斷介面，可檢查：
- CDN 資源載入狀態
- API 連線狀態
- 瀏覽器環境
- 錯誤日誌

**使用方式:**
```
http://localhost:8000/static/chart-debug.html
```

### 3. 建立備用方案 ✅

**檔案:** `static/js/realtime-chart-fallback.js`

當外部 API 無法使用時，自動切換到模擬數據。

### 4. 建立測試腳本 ✅

**檔案:** `test_chart_api.py`

快速測試 API 連線狀態。

**使用方式:**
```bash
python test_chart_api.py
```

## 如何解決問題

### 步驟 1: 清除瀏覽器快取

最常見的問題是瀏覽器快取了舊版本的 JavaScript。

**Windows:**
```
Ctrl + Shift + Delete
或
Ctrl + F5 (強制重新載入)
```

**Mac:**
```
Cmd + Shift + Delete
或
Cmd + Shift + R (強制重新載入)
```

### 步驟 2: 開啟診斷工具

訪問診斷頁面檢查具體問題：
```
http://localhost:8000/static/chart-debug.html
```

### 步驟 3: 檢查瀏覽器控制台

按 `F12` 開啟開發者工具，查看 Console 分頁：

**正常情況應該看到:**
```
即時圖表初始化完成
```

**如果看到錯誤:**
- `LightweightCharts is not defined` → CDN 載入失敗
- `Failed to fetch` → 網路問題
- 其他錯誤 → 查看詳細訊息

### 步驟 4: 檢查網路請求

在開發者工具的 Network 分頁，確認：

1. ✅ `lightweight-charts.standalone.production.js` (狀態 200)
2. ✅ `realtime-chart.js?v=2` (狀態 200)
3. ✅ `/api/kbars/TXF?...` (狀態 200)

## 可能的問題與解決方案

### 問題 1: CDN 載入失敗

**症狀:** 控制台顯示 `LightweightCharts is not defined`

**解決方案:**

修改 `static/dashboard.html`，使用備用 CDN：

```html
<!-- 原本 -->
<script src="https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>

<!-- 改為 -->
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"></script>
```

### 問題 2: 圖表容器找不到

**症狀:** 控制台顯示 `找不到圖表容器 #chartContainer`

**解決方案:**

確認 HTML 中有圖表容器：
```html
<div id="chartContainer" class="chart-container"></div>
```

### 問題 3: 非交易時段無數據

**症狀:** 圖表狀態顯示「無數據（非交易時段或週末）」

**說明:** 這是正常現象

**台灣期貨交易時間:**
- 日盤: 08:45 - 13:45
- 夜盤: 15:00 - 05:00 (次日)
- 週末及國定假日休市

**解決方案:**
- 等待交易時段再測試
- 或載入備用方案使用模擬數據

### 問題 4: CORS 錯誤

**症狀:** 控制台顯示 CORS policy 錯誤

**解決方案:**

這通常不會發生，因為 API 已設定 CORS。如果遇到：
1. 確認使用 `http://localhost:8000` 而非 `file://`
2. 檢查防火牆設定

## 使用備用方案（模擬數據）

如果外部 API 持續無法使用，可以啟用備用方案：

在 `static/dashboard.html` 中加入：

```html
<script src="/static/js/realtime-chart-fallback.js?v=1"></script>
```

放在 `realtime-chart.js` 之後。

## 驗證修復

### 1. 重啟服務
```bash
# 停止現有服務
# 重新啟動
python main.py
```

### 2. 清除快取並重新載入
```
Ctrl + Shift + Delete (清除快取)
Ctrl + F5 (強制重新載入)
```

### 3. 切換到圖表分頁

應該看到：
- ✅ 圖表正常顯示
- ✅ K 線數據載入
- ✅ 支撐壓力線顯示
- ✅ 狀態顯示「TXF 即時」

## 檔案變更清單

```
修改:
  static/js/realtime-chart.js (v1 → v2)
  static/dashboard.html (更新版本號)

新增:
  static/chart-debug.html (診斷工具)
  static/js/realtime-chart-fallback.js (備用方案)
  test_chart_api.py (API 測試腳本)
  CHART_TROUBLESHOOTING.md (故障排除指南)
  CHART_FIX_SUMMARY.md (本檔案)
```

## 下一步

1. **清除瀏覽器快取** (最重要！)
2. **訪問診斷頁面** 確認所有檢查通過
3. **開啟圖表分頁** 查看是否正常載入
4. **如果仍有問題** 查看瀏覽器控制台的錯誤訊息

## 技術支援

如果問題仍未解決，請提供：
1. 瀏覽器控制台的完整錯誤訊息（截圖）
2. 診斷工具的檢測結果（截圖）
3. 瀏覽器版本和作業系統資訊

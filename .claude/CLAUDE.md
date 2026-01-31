# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 語言偏好
**重要: 所有互動必須使用繁體中文**
- 所有回應、程式碼註解、文件、Commit 訊息使用繁體中文

---

## 常用指令

### 測試
```bash
# 執行所有測試
pytest tests/ -v

# 執行單一測試檔案
pytest tests/test_trading_queue.py -v

# 執行特定測試函數
pytest tests/test_trading_queue.py::TestTradingRequest::test_to_json_應該正確序列化 -v

# 執行測試並顯示覆蓋率
pytest tests/ -v --cov=. --cov-report=term-missing
```

### 本地開發
```bash
# 安裝依賴
pip install -r requirements.txt
pip install pytest pytest-cov  # 測試依賴

# 啟動 Redis (需先安裝)
redis-server

# 啟動 Trading Worker
python trading_worker.py

# 啟動 API 開發伺服器
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker
```bash
# 啟動所有服務 (Windows/Linux/macOS)
docker compose up -d

# 重建映像並啟動
docker compose up -d --build

# 查看日誌
docker compose logs -f              # 所有服務
docker compose logs -f api          # API 服務
docker compose logs -f trading-worker  # Trading Worker

# 停止服務
docker compose down

# 重置資料庫（清除所有資料）
docker compose down && docker volume rm shioaji-api-dashboard_postgres_data shioaji-api-dashboard_redis_data && docker compose up -d
```

---

## 架構概覽

### 核心元件互動流程
```
HTTP 請求 → NGINX (IP 白名單) → FastAPI (main.py) → Redis Queue → Trading Worker → Shioaji API
                                       ↓
                                  PostgreSQL (訂單紀錄)
```

### 主要模組職責

| 模組 | 職責 |
|------|------|
| `main.py` | FastAPI 應用程式，處理 HTTP/WebSocket 請求 |
| `trading_worker.py` | 維護 Shioaji 單一連線，處理 Redis 佇列請求，自動重連 |
| `trading_queue.py` | Redis 請求/回應佇列介面 (TradingRequest/TradingResponse) |
| `trading.py` | Shioaji 交易邏輯共用函數（登入、下單、持倉查詢） |
| `quote_manager.py` | 即時報價訂閱管理，透過 Redis Pub/Sub 發布更新 |
| `websocket_manager.py` | 前端 WebSocket 連線管理，廣播報價給訂閱客戶端 |
| `config.py` | Pydantic Settings 統一配置管理 |
| `models.py` | SQLAlchemy ORM 模型 (OrderHistory) |
| `status_mapper.py` | Shioaji 狀態到系統內部狀態的映射 |

### 關鍵設計模式

1. **單一連線架構**: Trading Worker 維護唯一的 Shioaji 連線，避免 "Too Many Connections" 錯誤。所有 API 請求透過 Redis 佇列與 Worker 通訊。

2. **請求/回應模式**:
   - `TradingRequest` → Redis Queue (`trading:requests`) → Trading Worker 處理
   - Worker 處理完畢 → Redis Key (`trading:response:{request_id}`) → API 取得回應

3. **自動重連**: Trading Worker 在 Token 過期或連線錯誤時自動重試（最多 3 次）。

4. **即時報價**: Shioaji 回調 → QuoteManager → Redis Pub/Sub → WebSocketManager → 前端

---

## 開發規範

### TDD (測試驅動開發)
1. 🔴 **紅燈**: 先寫失敗的測試
2. 🟢 **綠燈**: 寫最少的程式碼讓測試通過
3. 🔄 **重構**: 改善程式碼品質，確保測試仍通過

### SOLID 原則
- **S**: 每個類別只做一件事
- **O**: 對擴展開放，對修改封閉
- **L**: 子類別可替換父類別
- **I**: 介面要小而專一
- **D**: 依賴抽象，使用依賴注入

### 測試命名規範
使用繁體中文描述測試意圖：
```python
def test_create_user_應該驗證資料(self):
def test_create_user_當驗證失敗時應該拋出例外(self):
```

### 開發檢查清單
- [ ] 先寫測試案例（涵蓋正常與邊界情況）
- [ ] 使用依賴注入而非硬編碼依賴
- [ ] 重構後測試仍通過
- [ ] 程式碼已格式化
- [ ] 有適當的繁體中文註解

# Simulation 模式整合測試指南

## 測試目的
驗證 API 端點正確處理模擬/實盤模式的篩選與記錄功能。

## 前置條件
1. 啟動 FastAPI 服務：`python main.py`
2. 確保資料庫已執行 migration：`bash db/migrate.sh`

## 手動測試案例

### 1. 測試下單時記錄模式

#### 1.1 模擬模式下單（預設）
```bash
curl -X POST "http://localhost:8000/api/orders" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "TXF",
    "action": "Buy",
    "quantity": 1,
    "price_type": "LMT",
    "order_type": "ROD"
  }'
```
**預期結果：** 回應中 `simulation: true`

#### 1.2 模擬模式下單（明確指定）
```bash
curl -X POST "http://localhost:8000/api/orders?simulation=true" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "TXF",
    "action": "Buy",
    "quantity": 1,
    "price_type": "LMT",
    "order_type": "ROD"
  }'
```
**預期結果：** 回應中 `simulation: true`

#### 1.3 實盤模式下單
```bash
curl -X POST "http://localhost:8000/api/orders?simulation=false" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "TXF",
    "action": "Sell",
    "quantity": 1,
    "price_type": "LMT",
    "order_type": "ROD"
  }'
```
**預期結果：** 回應中 `simulation: false`

### 2. 測試查詢訂單時依模式篩選

#### 2.1 查詢所有訂單（不篩選）
```bash
curl "http://localhost:8000/api/orders"
```
**預期結果：** 回傳所有訂單，包含模擬與實盤

#### 2.2 只查詢模擬模式訂單
```bash
curl "http://localhost:8000/api/orders?simulation=true"
```
**預期結果：** 只回傳 `simulation: true` 的訂單

#### 2.3 只查詢實盤模式訂單
```bash
curl "http://localhost:8000/api/orders?simulation=false"
```
**預期結果：** 只回傳 `simulation: false` 的訂單

#### 2.4 組合篩選（模式 + 商品）
```bash
curl "http://localhost:8000/api/orders?simulation=true&symbol=TXF"
```
**預期結果：** 只回傳模擬模式且商品為 TXF 的訂單

#### 2.5 組合篩選（模式 + 動作）
```bash
curl "http://localhost:8000/api/orders?simulation=false&action=Buy"
```
**預期結果：** 只回傳實盤模式且動作為 Buy 的訂單

### 3. 測試匯出訂單時依模式篩選

#### 3.1 匯出模擬模式訂單（CSV）
```bash
curl "http://localhost:8000/api/orders/export?simulation=true&format=csv" \
  -o simulation_orders.csv
```
**預期結果：** CSV 檔案只包含模擬模式訂單

#### 3.2 匯出實盤模式訂單（JSON）
```bash
curl "http://localhost:8000/api/orders/export?simulation=false&format=json" \
  -o production_orders.json
```
**預期結果：** JSON 檔案只包含實盤模式訂單

## 資料庫驗證

### 檢查 simulation 欄位
```sql
-- 查看所有訂單的模式分布
SELECT simulation, COUNT(*) as count 
FROM order_history 
GROUP BY simulation;

-- 查看模擬模式訂單
SELECT id, symbol, action, quantity, simulation, created_at 
FROM order_history 
WHERE simulation = 1 
ORDER BY created_at DESC 
LIMIT 10;

-- 查看實盤模式訂單
SELECT id, symbol, action, quantity, simulation, created_at 
FROM order_history 
WHERE simulation = 0 
ORDER BY created_at DESC 
LIMIT 10;
```

## 自動化測試建議

未來可以使用 pytest + httpx 撰寫自動化整合測試：

```python
import httpx
import pytest

@pytest.mark.asyncio
async def test_create_order_simulation_mode():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        response = await client.post(
            "/api/orders?simulation=true",
            json={
                "symbol": "TXF",
                "action": "Buy",
                "quantity": 1,
                "price_type": "LMT",
                "order_type": "ROD"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["simulation"] is True
```

## 注意事項

1. 測試前確保 Shioaji API 已登入
2. 模擬模式不會真的送單到交易所
3. 實盤模式測試請小心，會產生真實委託
4. 測試完成後記得清理測試資料

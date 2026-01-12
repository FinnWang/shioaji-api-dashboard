# 📝 期權交易設定指南

## 目前狀態

✅ **系統已支援期權交易**
- 已新增期權合約查詢功能
- 可以查詢 TXO（台指選擇權）合約
- 下單邏輯已支援期權

❌ **API Token 權限不足**
- 目前 Token 權限：`["Portfolio", "Data"]`（只有查詢權限）
- 需要權限：`["Portfolio", "Data", "Trading"]`（需要交易權限）

## 問題說明

從日誌可以看到：
```
"permissions":["Portfolio","Data"]
```

即使你已經申請了期權交易帳戶，**API Token 本身也需要有交易權限**。

## 解決方法

### 方案 1：申請具有交易權限的 API Token（推薦）

1. **聯絡永豐金證券客服**
   - 電話：(02) 2312-3866
   - 或透過永豐金證券 APP 聯絡客服

2. **說明需求**
   - 告知已有期權交易帳戶
   - 需要申請 **Shioaji API 交易權限**
   - 說明要用於程式交易

3. **取得新的 API Token**
   - 審核通過後會給你新的 `API_KEY` 和 `SECRET_KEY`
   - 新 Token 會包含 `Trading` 權限

4. **更新 .env 檔案**
   ```env
   API_KEY=新的_api_key
   SECRET_KEY=新的_secret_key
   ```

5. **重啟服務**
   ```bash
   docker compose restart trading-worker api
   ```

### 方案 2：使用永豐金證券網頁版測試

如果暫時無法取得交易權限的 API Token，可以：
1. 使用永豐金證券網頁版或 APP 手動下單
2. 用本系統查詢持倉、損益等資訊
3. 等取得交易權限後再使用自動下單功能

## 目前可用功能

即使沒有交易權限，以下功能仍可使用：

### ✅ 查詢功能（可用）

1. **查詢期權合約**
   ```bash
   curl "http://localhost:9879/symbols?simulation=true"
   ```

2. **查詢持倉**
   ```bash
   curl -H "X-Auth-Key: your_key" \
     "http://localhost:9879/positions?simulation=true"
   ```

3. **查詢保證金**
   ```bash
   curl -H "X-Auth-Key: your_key" \
     "http://localhost:9879/margin?simulation=true"
   ```

4. **查詢損益**
   ```bash
   curl -H "X-Auth-Key: your_key" \
     "http://localhost:9879/profit-loss?simulation=true"
   ```

5. **查詢成交紀錄**
   ```bash
   curl -H "X-Auth-Key: your_key" \
     "http://localhost:9879/trades?simulation=true"
   ```

### ❌ 下單功能（需要權限）

```bash
# 這個會失敗，因為沒有交易權限
curl -X POST "http://localhost:9879/order?simulation=true" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "long_entry",
    "symbol": "TXO20260229800C",
    "quantity": 1
  }'
```

錯誤訊息：
```
Token doesn't have permission
```

## 期權合約範例

系統已支援的期權合約格式：

```json
{
  "symbol": "TXO20260229800C",
  "code": "TXO29800B6",
  "name": "台指選擇權F502月29800C",
  "type": "options"
}
```

說明：
- `TXO` = 台指選擇權
- `202602` = 2026年2月
- `29800` = 履約價
- `C` = Call（買權），`P` = Put（賣權）

## 測試步驟（取得權限後）

1. **查詢可用的期權合約**
   ```bash
   curl "http://localhost:9879/symbols?simulation=true" | jq '.symbols[] | select(.type=="options") | .symbol' | head -5
   ```

2. **選擇一個合約下單**
   ```bash
   curl -X POST "http://localhost:9879/order?simulation=true" \
     -H "Content-Type: application/json" \
     -d '{
       "action": "long_entry",
       "symbol": "TXO20260229800C",
       "quantity": 1
     }'
   ```

3. **查詢委託紀錄**
   ```bash
   curl -H "X-Auth-Key: your_key" \
     "http://localhost:9879/orders?limit=10"
   ```

## Dashboard 使用

1. 開啟 http://localhost:9879/dashboard
2. 輸入驗證金鑰
3. 點擊「可用商品」分頁
4. 可以看到所有期貨和期權合約
5. 期權合約會標示 `type: options`

## 下一步

1. ✅ 系統已支援期權交易
2. ⏳ 等待取得具有交易權限的 API Token
3. 🎯 取得後即可開始期權自動交易

## 聯絡資訊

**永豐金證券客服**
- 電話：(02) 2312-3866
- 營業時間：週一至週五 08:30-17:30
- 線上客服：永豐金證券 APP

**需要說明的重點**
- 已有期權交易帳戶
- 需要 Shioaji API 的**交易權限**（Trading permission）
- 用於程式交易（Algorithmic Trading）

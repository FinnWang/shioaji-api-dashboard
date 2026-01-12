# 🧪 API 測試指南

## 目前狀態

你的 Shioaji API Token 權限：
- ✅ **Portfolio**（持倉查詢）
- ✅ **Data**（資料查詢）
- ❌ **Trading**（下單權限）- 需要額外申請

## 可用的 API 端點

### 1. 查詢持倉 ✅
```bash
curl -X GET "http://localhost:9879/positions?simulation=true" \
  -H "X-Auth-Key: your_secure_auth_key_here"
```

### 2. 查詢保證金 ✅
```bash
curl -X GET "http://localhost:9879/margin?simulation=true" \
  -H "X-Auth-Key: your_secure_auth_key_here"
```

### 3. 查詢損益 ✅
```bash
curl -X GET "http://localhost:9879/profit-loss?simulation=true" \
  -H "X-Auth-Key: your_secure_auth_key_here"
```

### 4. 查詢成交紀錄 ✅
```bash
curl -X GET "http://localhost:9879/trades?simulation=true" \
  -H "X-Auth-Key: your_secure_auth_key_here"
```

### 5. 查詢結算資料 ✅
```bash
curl -X GET "http://localhost:9879/settlements?simulation=true" \
  -H "X-Auth-Key: your_secure_auth_key_here"
```

### 6. 查詢可用商品 ✅
```bash
curl -X GET "http://localhost:9879/symbols?simulation=true"
```

### 7. 查詢期貨合約 ✅
```bash
curl -X GET "http://localhost:9879/futures?simulation=true"
```

## 下單功能（需要交易權限）

### 8. 下單 ❌ (需要申請權限)
```bash
curl -X POST "http://localhost:9879/order?simulation=true" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "long_entry",
    "symbol": "MXFR1",
    "quantity": 1
  }'
```

## 如何申請交易權限

1. 聯絡永豐金證券客服
2. 說明需要申請 **Shioaji API 交易權限**
3. 提供你的帳號資訊
4. 等待審核通過後，重新取得 API Token

## PowerShell 測試範例

```powershell
# 查詢持倉
Invoke-WebRequest -Uri "http://localhost:9879/positions?simulation=true" `
  -Headers @{"X-Auth-Key"="your_secure_auth_key_here"} `
  -UseBasicParsing | Select-Object -ExpandProperty Content

# 查詢保證金
Invoke-WebRequest -Uri "http://localhost:9879/margin?simulation=true" `
  -Headers @{"X-Auth-Key"="your_secure_auth_key_here"} `
  -UseBasicParsing | Select-Object -ExpandProperty Content

# 查詢損益
Invoke-WebRequest -Uri "http://localhost:9879/profit-loss?simulation=true" `
  -Headers @{"X-Auth-Key"="your_secure_auth_key_here"} `
  -UseBasicParsing | Select-Object -ExpandProperty Content
```

## Python 測試範例

```python
import requests

API_URL = "http://localhost:9879"
AUTH_KEY = "your_secure_auth_key_here"
HEADERS = {"X-Auth-Key": AUTH_KEY}

# 查詢持倉
positions = requests.get(f"{API_URL}/positions?simulation=true", headers=HEADERS).json()
print("持倉:", positions)

# 查詢保證金
margin = requests.get(f"{API_URL}/margin?simulation=true", headers=HEADERS).json()
print("保證金:", margin)

# 查詢損益
pnl = requests.get(f"{API_URL}/profit-loss?simulation=true", headers=HEADERS).json()
print("損益:", pnl)

# 查詢成交紀錄
trades = requests.get(f"{API_URL}/trades?simulation=true", headers=HEADERS).json()
print("成交紀錄:", trades)
```

## 注意事項

1. **模擬帳戶資料為空是正常的**
   - 沒有實際交易，所以成交紀錄、損益都是 0
   - 保證金資訊也可能是 0

2. **實盤交易需要**
   - CA 憑證（Sinopac.pfx）
   - 設定 `simulation=false`
   - 更新 `.env` 檔案中的 CA 相關設定

3. **API 文件**
   - 開啟 http://localhost:9879/docs 查看完整 API 文件
   - 可以直接在文件頁面測試所有 API

## 目前系統功能總結

✅ **已完成並可用：**
- 查詢持倉
- 查詢保證金
- 查詢損益
- 查詢成交紀錄
- 查詢結算資料
- 查詢可用商品
- Web Dashboard UI
- API 文件

⏳ **需要權限才能使用：**
- 下單功能（需要向永豐金申請交易權限）

🎯 **建議下一步：**
1. 先使用查詢功能熟悉系統
2. 向永豐金申請交易權限
3. 取得權限後即可使用完整下單功能

# 即時報價訂閱系統

本文件說明 Shioaji 期貨報價訂閱的實作方式，包含 Tick（逐筆成交）和 BidAsk（五檔報價）兩種資料類型。

## 架構概覽

```
┌─────────────────┐     WebSocket      ┌─────────────────┐
│                 │◄──────────────────►│                 │
│   前端 Browser  │                    │   FastAPI API   │
│                 │                    │                 │
└─────────────────┘                    └────────┬────────┘
                                                │
                                         Redis Pub/Sub
                                                │
                                       ┌────────▼────────┐
                                       │                 │
                                       │ Trading Worker  │
                                       │                 │
                                       └────────┬────────┘
                                                │
                                         QuoteManager
                                                │
                                       ┌────────▼────────┐
                                       │                 │
                                       │   Shioaji API   │
                                       │                 │
                                       └─────────────────┘
```

## 資料類型比較

| 類型 | QuoteType | 回調函數 | 包含資料 | 更新頻率 |
|------|-----------|----------|----------|----------|
| **Tick** | `QuoteType.Tick` | `@api.on_tick_fop_v1()` | 成交價、成交量、開高低收、漲跌幅 | 每筆成交 |
| **BidAsk** | `QuoteType.BidAsk` | `@api.on_bidask_fop_v1()` | 五檔買賣價、委託量 | 委託簿變動 |

### Tick 資料欄位
```python
TickFOPv1:
    code: str           # 合約代碼 (如 MXFC6)
    datetime: datetime  # 時間戳
    open: float         # 開盤價
    high: float         # 最高價
    low: float          # 最低價
    close: float        # 成交價（現價）
    volume: int         # 單筆成交量
    total_volume: int   # 累計成交量
    price_chg: float    # 漲跌點數
    pct_chg: float      # 漲跌幅 (%)
```

### BidAsk 資料欄位
```python
BidAskFOPv1:
    code: str              # 合約代碼
    datetime: datetime     # 時間戳
    bid_price: List[float] # 委買價 (5檔)
    bid_volume: List[int]  # 委買量 (5檔)
    ask_price: List[float] # 委賣價 (5檔)
    ask_volume: List[int]  # 委賣量 (5檔)
```

## 訂閱流程

### 1. 前端發起訂閱

```javascript
// static/js/dashboard.js
function subscribeQuote(symbol) {
    quoteWebSocket.send(JSON.stringify({
        type: 'subscribe',
        symbol: symbol,           // 如 "MXFR1" 或 "MXF202603"
        simulation: simulationMode
    }));
}
```

### 2. API 接收 WebSocket 訊息

```python
# main.py - WebSocket 端點
@app.websocket("/ws/quotes")
async def websocket_quotes_endpoint(websocket: WebSocket):
    # ... 連線處理 ...

    if msg_type == "subscribe":
        symbol = data.get("symbol")
        simulation = data.get("simulation", True)

        # 註冊 WebSocket 訂閱
        await ws_manager.subscribe_symbol(client_id, symbol)

        # 透過 Redis Queue 請求 Trading Worker 訂閱
        response = queue_client.subscribe_quote(
            symbol=symbol,
            simulation=simulation
        )
```

### 3. Trading Worker 處理訂閱

```python
# trading_worker.py
def handle_subscribe_quote(request):
    symbol = request["symbol"]
    simulation = request["simulation"]

    # 取得合約
    contract = get_futures_contract(api, symbol)

    # 透過 QuoteManager 訂閱
    quote_manager.subscribe(symbol, contract)
```

### 4. QuoteManager 訂閱 Shioaji

```python
# quote_manager.py
def subscribe(self, symbol: str, contract: Any) -> bool:
    # 訂閱 Tick 資料
    self._api.quote.subscribe(
        contract,
        quote_type=sj.constant.QuoteType.Tick,
    )

    # 訂閱 BidAsk 資料
    self._api.quote.subscribe(
        contract,
        quote_type=sj.constant.QuoteType.BidAsk,
    )

    # 建立 code 映射（處理別名合約）
    self._code_to_symbol[contract.code] = symbol
```

## 報價回調處理

### 設置回調函數

```python
# quote_manager.py
def setup_quote_callback(self) -> None:
    manager = self

    @self._api.on_tick_fop_v1()
    def on_tick_fop(exchange: Exchange, tick: TickFOPv1):
        manager._handle_tick_fop(exchange, tick)

    @self._api.on_bidask_fop_v1()
    def on_bidask_fop(exchange: Exchange, bidask: BidAskFOPv1):
        manager._handle_bidask_fop(exchange, bidask)
```

### 處理 Tick 回調

```python
def _handle_tick_fop(self, exchange: Exchange, tick: TickFOPv1) -> None:
    code = tick.code
    symbol = self._code_to_symbol.get(code)

    # 動態映射（處理別名合約 TMFR1 -> TMFC6）
    if symbol is None:
        symbol = self._try_create_dynamic_mapping(code)

    # 建立報價資料
    quote_data = QuoteData(
        symbol=symbol,
        code=code,
        quote_type="tick",
        close=tick.close,
        open=tick.open,
        high=tick.high,
        low=tick.low,
        change_price=tick.price_chg,
        change_rate=tick.pct_chg,
        volume=tick.volume,
        total_volume=tick.total_volume,
        # ...
    )

    # 發布到 Redis
    channel = f"quote:{symbol}"
    self._redis.publish(channel, quote_data.to_json())
```

### 處理 BidAsk 回調

```python
def _handle_bidask_fop(self, exchange: Exchange, bidask: BidAskFOPv1) -> None:
    code = bidask.code
    symbol = self._code_to_symbol.get(code)

    # 取得最佳買賣價（第一檔）
    bid_price = bidask.bid_price[0]
    ask_price = bidask.ask_price[0]
    bid_volume = bidask.bid_volume[0]
    ask_volume = bidask.ask_volume[0]

    quote_data = QuoteData(
        symbol=symbol,
        code=code,
        quote_type="bidask",
        buy_price=bid_price,
        sell_price=ask_price,
        buy_volume=bid_volume,
        sell_volume=ask_volume,
        # ...
    )

    channel = f"quote:{symbol}"
    self._redis.publish(channel, quote_data.to_json())
```

## Redis Pub/Sub 廣播

### WebSocketManager 監聽

```python
# websocket_manager.py
async def start_pubsub_listener(self) -> None:
    pubsub = self._redis.pubsub()
    await pubsub.psubscribe("quote:*")

    while self._running:
        message = await pubsub.get_message()
        if message:
            channel = message["channel"]  # "quote:MXFR1"
            data = message["data"]
            await self._handle_redis_message(channel, data)

async def _handle_redis_message(self, channel: str, data: str) -> None:
    symbol = channel.replace("quote:", "")
    quote_data = json.loads(data)

    message = {
        "type": "quote",
        "symbol": symbol,
        "data": quote_data,
    }

    # 廣播給訂閱該商品的客戶端
    await self.broadcast_to_symbol(symbol, message)
```

## 前端報價更新

```javascript
// static/js/dashboard.js
function handleQuoteUpdate(symbol, data) {
    const quoteType = data.quote_type || 'tick';

    // Tick 資料：更新成交價、漲跌
    if (quoteType === 'tick' && data.close) {
        document.getElementById('currentPrice').textContent = data.close;
        document.getElementById('priceChange').textContent =
            `${data.change_price} (${data.change_rate}%)`;
        document.getElementById('totalVolume').textContent = data.total_volume;
    }

    // BidAsk 資料：更新買賣價
    if (quoteType === 'bidask') {
        document.getElementById('buyPrice').textContent = data.buy_price;
        document.getElementById('sellPrice').textContent = data.sell_price;
        document.getElementById('buyVolume').textContent = data.buy_volume;
        document.getElementById('sellVolume').textContent = data.sell_volume;
    }
}
```

## 別名合約處理

期貨有「別名合約」的概念：
- `MXFR1` = 小台指近月
- `MXFR2` = 小台指次月
- `TMFR1` = 台指近月

訂閱別名時，Shioaji 返回的報價 code 是實際合約代碼（如 `MXFC6`），需要動態映射：

```python
def _try_create_dynamic_mapping(self, code: str) -> Optional[str]:
    for subscribed_symbol, contract in self._subscriptions.items():
        # 檢查是否是別名合約
        if subscribed_symbol.endswith('R1') or subscribed_symbol.endswith('R2'):
            base_code = subscribed_symbol[:-2]  # MXF, TMF, TXF

            # 比對前 3 字元
            if code[:3] == base_code[:3]:
                self._code_to_symbol[code] = subscribed_symbol
                return subscribed_symbol

    return None
```

## 完整資料流

```
1. 用戶選擇商品 (MXFR1)
       │
       ▼
2. 前端 WebSocket 發送 subscribe
       │
       ▼
3. API 透過 Redis Queue 請求訂閱
       │
       ▼
4. Trading Worker 呼叫 QuoteManager.subscribe()
       │
       ├─► api.quote.subscribe(contract, QuoteType.Tick)
       │
       └─► api.quote.subscribe(contract, QuoteType.BidAsk)

5. Shioaji 推送報價
       │
       ├─► on_tick_fop_v1(tick)    → _handle_tick_fop()
       │                                    │
       │                                    ▼
       │                           Redis publish "quote:MXFR1"
       │
       └─► on_bidask_fop_v1(bidask) → _handle_bidask_fop()
                                            │
                                            ▼
                                   Redis publish "quote:MXFR1"

6. WebSocketManager 監聽 Redis "quote:*"
       │
       ▼
7. 廣播給訂閱 MXFR1 的 WebSocket 客戶端
       │
       ▼
8. 前端 handleQuoteUpdate() 更新 UI
```

## 相關檔案

| 檔案 | 說明 |
|------|------|
| `quote_manager.py` | 報價訂閱管理、Shioaji 回調處理 |
| `websocket_manager.py` | WebSocket 連線管理、Redis Pub/Sub 監聽 |
| `trading_worker.py` | 訂閱請求處理 |
| `main.py` | WebSocket 端點 `/ws/quotes` |
| `static/js/dashboard.js` | 前端 WebSocket 連線、報價更新 |

## 注意事項

1. **訂閱限制**: Shioaji 每帳號最多 200 個訂閱
2. **交易時間**:
   - 日盤: 08:45 - 13:45
   - 夜盤: 15:00 - 05:00
3. **多進程**: FastAPI 多 worker 環境下，只有持有 WebSocket 連線的 worker 會廣播報價

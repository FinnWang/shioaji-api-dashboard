# Shioaji API 開發指南

> 本專案使用 Shioaji - 台灣最受歡迎的跨平台交易 API，支援 Windows、Linux、Mac，可交易股票、期貨、選擇權。

## 登入與認證

### Token 登入 (v1.0+)
```python
import shioaji as sj
api = sj.Shioaji()
api.login(
    api_key="YOUR_API_KEY", 
    secret_key="YOUR_SECRET_KEY",
    contracts_timeout=10000,  # 等待商品檔下載 (ms)
    subscribe_trade=True,     # 訂閱委託/成交回報
)
```

### 登入參數
- `api_key`: API 金鑰
- `secret_key`: 密鑰
- `fetch_contract`: 是否下載商品檔 (預設: True)
- `contracts_timeout`: 商品檔 timeout (預設: 0 ms)
- `subscribe_trade`: 訂閱委託/成交回報 (預設: True)
- `receive_window`: 登入有效時間 (預設: 30,000 ms)

### 模擬環境
```python
api = sj.Shioaji(simulation=True)
```

## 商品檔 (Contracts)

### 取得商品
```python
# 證券
api.Contracts.Stocks["2890"]
api.Contracts.Stocks.TSE.TSE2890

# 期貨
api.Contracts.Futures["TXFA3"]
api.Contracts.Futures.TXF.TXF202301

# 選擇權
api.Contracts.Options["TXO18000R3"]
api.Contracts.Options.TXO.TXO20230618000P

# 指數 (僅供訂閱行情，不可下單)
api.Contracts.Indexs.TSE["001"]
```

### 商品檔更新時間
- 07:50 期貨商品檔更新
- 08:00 全市場商品檔更新
- 14:45 期貨夜盤商品檔更新
- 17:15 期貨夜盤商品檔更新

## 帳號管理

```python
# 帳號列表
accounts = api.list_accounts()

# 預設帳號
api.stock_account      # 證券預設帳號
api.futopt_account     # 期貨預設帳號

# 設定預設帳號
api.set_default_account(accounts[1])
```

## 下單 API

### 證券下單
```python
contract = api.Contracts.Stocks["2890"]
order = api.Order(
    price=16, 
    quantity=1, 
    action=sj.constant.Action.Buy,           # Buy/Sell
    price_type=sj.constant.StockPriceType.LMT,  # LMT/MKT
    order_type=sj.constant.OrderType.ROD,    # ROD/IOC/FOK
    order_lot=sj.constant.StockOrderLot.Common,  # Common/Odd/IntradayOdd
    order_cond=sj.constant.StockOrderCond.Cash,  # Cash/MarginTrading/ShortSelling
    account=api.stock_account
)
trade = api.place_order(contract, order)
```

### 期貨下單
```python
contract = api.Contracts.Futures.TXF.TXF202301
order = api.Order(
    action=sj.constant.Action.Buy,
    price=14400,
    quantity=3,
    price_type=sj.constant.FuturesPriceType.LMT,  # LMT/MKT/MKP
    order_type=sj.constant.OrderType.ROD,
    octype=sj.constant.FuturesOCType.Auto,  # Auto/New/Cover/DayTrade
    account=api.futopt_account
)
trade = api.place_order(contract, order)
```

### 委託操作
```python
# 更新委託狀態
api.update_status(api.stock_account)

# 查詢委託
trades = api.list_trades()

# 改價
api.update_order(trade, price=new_price)

# 改量
api.update_order(trade, quantity=new_qty)

# 刪單
api.cancel_order(trade)
```

## 行情訂閱

### 訂閱即時行情
```python
# 訂閱 Tick
api.quote.subscribe(
    api.Contracts.Stocks["2330"], 
    quote_type=sj.constant.QuoteType.Tick,
    version=sj.constant.QuoteVersion.v1
)

# 訂閱 BidAsk
api.quote.subscribe(
    contract,
    quote_type=sj.constant.QuoteType.BidAsk,
    version=sj.constant.QuoteVersion.v1
)

# 盤中零股
api.quote.subscribe(
    contract,
    quote_type=sj.constant.QuoteType.Tick,
    intraday_odd=True
)
```

### 行情 Callback
```python
from shioaji import TickSTKv1, Exchange

@api.on_tick_stk_v1()
def quote_callback(exchange: Exchange, tick: TickSTKv1):
    print(f"Exchange: {exchange}, Tick: {tick}")

@api.on_bidask_stk_v1()
def bidask_callback(exchange: Exchange, bidask: BidAskSTKv1):
    print(f"Exchange: {exchange}, BidAsk: {bidask}")
```

### 歷史資料查詢
```python
# Ticks
ticks = api.ticks(contract=api.Contracts.Stocks["2330"], date="2023-01-16")

# KBars
kbars = api.kbars(contract=api.Contracts.Stocks["2330"], start="2023-01-15", end="2023-01-16")

# 市場快照 (最多500檔)
snapshots = api.snapshots([contract1, contract2])
```

## 帳務查詢

### 證券
```python
# 帳戶餘額
api.account_balance()

# 未實現損益
positions = api.list_positions(api.stock_account)

# 已實現損益
profitloss = api.list_profit_loss(api.stock_account, '2020-05-05', '2020-05-30')

# 交割款
settlements = api.settlements(api.stock_account)

# 交易額度
limits = api.trading_limits(api.stock_account)
```

### 期貨
```python
# 保證金
margin = api.margin(api.futopt_account)

# 未實現損益
positions = api.list_positions(api.futopt_account)
```

## 委託/成交回報

```python
def order_cb(stat, msg):
    print(stat, msg)

api.set_order_callback(order_cb)
```

## API 使用限制

### 流量限制
| 近30日成交金額 | 每日流量限制 |
|--------------|------------|
| 0 | 500MB |
| 1 - 1億 | 2GB |
| > 1億 | 10GB |

### 次數限制
- 行情查詢: 5秒上限 50次
- 帳務查詢: 5秒上限 25次
- 委託操作: 10秒上限 250次
- 訂閱數: 200個
- 連線數: 同一 person_id 最多 5個連線
- 登入: 一天上限 1000次

### 查詢流量
```python
api.usage()
# UsageStatus(connections=1, bytes=41343260, limit_bytes=2147483648, remaining_bytes=2106140388)
```

## 非阻塞模式

```python
# 非阻塞下單 (timeout=0)
trade = api.place_order(contract, order, timeout=0)

# 非阻塞下單回調
def non_blocking_cb(trade: Trade):
    print(trade)

trade = api.place_order(contract, order, timeout=0, cb=non_blocking_cb)
```

## 連續期貨合約

使用 `R1`, `R2` 取得到期期貨的歷史資料：
```python
# 近月連續合約
api.Contracts.Futures.TXF.TXFR1
# 次月連續合約
api.Contracts.Futures.TXF.TXFR2
```

## 重要注意事項

1. 登入時若收到 "Sign data is timeout"，需校準電腦時間或調高 `receive_window`
2. 帳號若無 `signed=True`，需先簽署服務條款
3. 流量超過限制時，行情查詢將回傳空值
4. 使用量超過限制將暫停服務一分鐘
5. 不使用時請呼叫 `api.logout()` 釋放連線

"""
QuoteManager - 即時報價訂閱管理器

負責管理 Shioaji 即時報價訂閱，並透過 Redis Pub/Sub 發布報價更新。

功能：
- 訂閱/取消訂閱 Shioaji 即時報價
- 處理 Shioaji 期貨報價回調 (TickFOPv1)
- 透過 Redis Pub/Sub 發布報價給 WebSocket 客戶端
- 訂閱計數管理（多個客戶端可訂閱同一商品）
"""
import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional, Any

import redis
import shioaji as sj
from shioaji import Exchange, TickFOPv1, BidAskFOPv1

logger = logging.getLogger(__name__)

# Redis Pub/Sub channel 前綴
QUOTE_CHANNEL_PREFIX = "quote:"


@dataclass
class QuoteData:
    """
    即時報價資料結構

    統一的報價資料格式，用於 Redis 發布和前端顯示
    """
    symbol: str
    code: str = ""
    quote_type: str = "tick"  # "tick" 或 "bidask"
    close: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    change_price: float = 0.0
    change_rate: float = 0.0
    volume: int = 0
    total_volume: int = 0
    buy_price: float = 0.0
    sell_price: float = 0.0
    buy_volume: int = 0
    sell_volume: int = 0
    timestamp: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """轉換為字典"""
        return asdict(self)

    def to_json(self) -> str:
        """序列化為 JSON 字串"""
        return json.dumps(self.to_dict())


class QuoteManager:
    """
    即時報價訂閱管理器

    管理 Shioaji 即時報價訂閱，並透過 Redis Pub/Sub 發布報價更新。

    使用計數器追蹤每個商品的訂閱者數量，確保：
    - 第一個訂閱者訂閱時才呼叫 Shioaji API
    - 最後一個訂閱者取消時才取消 Shioaji 訂閱
    - 避免重複訂閱造成的 API 限制問題

    注意：Shioaji 每帳號最多 200 個訂閱
    """

    def __init__(self, api: sj.Shioaji, redis_client: redis.Redis):
        """
        初始化 QuoteManager

        Args:
            api: Shioaji API 實例
            redis_client: Redis 客戶端實例
        """
        self._api = api
        self._redis = redis_client

        # 追蹤已訂閱的合約 {symbol: contract}
        self._subscriptions: Dict[str, Any] = {}

        # 追蹤每個商品的訂閱者數量 {symbol: count}
        self._subscriber_counts: Dict[str, int] = {}

        # 追蹤 symbol 和 code 的對應關係 {code: symbol}
        self._code_to_symbol: Dict[str, str] = {}

        logger.info("QuoteManager 初始化完成")

    def setup_quote_callback(self) -> None:
        """
        設置 Shioaji 報價回調函數

        在 Worker 初始化時呼叫，註冊期貨專用的回調函數：
        - on_tick_fop_v1: 期貨/選擇權 Tick 資料
        - on_bidask_fop_v1: 期貨/選擇權五檔資料
        """
        # 保存 self 引用供回調使用
        manager = self

        # 設置期貨 Tick 回調
        @self._api.on_tick_fop_v1()
        def on_tick_fop(exchange: Exchange, tick: TickFOPv1):
            logger.info(f"[on_tick_fop_v1] 收到 Tick: code={tick.code}, close={tick.close}")
            manager._handle_tick_fop(exchange, tick)

        # 設置期貨 BidAsk 回調（可選，用於五檔報價）
        @self._api.on_bidask_fop_v1()
        def on_bidask_fop(exchange: Exchange, bidask: BidAskFOPv1):
            logger.debug(f"[on_bidask_fop_v1] 收到 BidAsk: code={bidask.code}")
            manager._handle_bidask_fop(exchange, bidask)

        logger.info("已設置 Shioaji 期貨回調 (on_tick_fop_v1, on_bidask_fop_v1)")

    def subscribe(self, symbol: str, contract: Any) -> bool:
        """
        訂閱商品報價

        如果是新訂閱，呼叫 Shioaji API 訂閱；
        如果已訂閱，只增加訂閱者計數。

        Args:
            symbol: 商品代碼（如 MXF202601）
            contract: Shioaji 合約物件

        Returns:
            訂閱成功返回 True，失敗返回 False
        """
        try:
            # 檢查是否已訂閱
            if symbol in self._subscriptions:
                # 已訂閱，增加計數
                self._subscriber_counts[symbol] = \
                    self._subscriber_counts.get(symbol, 0) + 1
                logger.debug(
                    f"商品 {symbol} 已訂閱，增加計數至 "
                    f"{self._subscriber_counts[symbol]}"
                )
                return True

            # 新訂閱，呼叫 Shioaji API
            # 同時訂閱 Tick（成交）和 BidAsk（五檔）資料
            logger.info(
                f"[訂閱] 呼叫 Shioaji API: symbol={symbol}, "
                f"contract.code={getattr(contract, 'code', 'N/A')}, "
                f"contract.symbol={getattr(contract, 'symbol', 'N/A')}"
            )
            # 訂閱 Tick 資料（成交價、成交量等）
            self._api.quote.subscribe(
                contract,
                quote_type=sj.constant.QuoteType.Tick,
            )
            # 訂閱 BidAsk 資料（五檔買賣價量）
            self._api.quote.subscribe(
                contract,
                quote_type=sj.constant.QuoteType.BidAsk,
            )

            # 記錄訂閱
            self._subscriptions[symbol] = contract
            self._subscriber_counts[symbol] = 1

            # 建立 code 到 symbol 的對應
            if hasattr(contract, 'code'):
                self._code_to_symbol[contract.code] = symbol
                logger.info(
                    f"[訂閱] 建立 code 映射: {contract.code} -> {symbol}, "
                    f"目前映射表: {self._code_to_symbol}"
                )

            logger.info(f"已訂閱商品 {symbol}，目前訂閱數: {len(self._subscriptions)}")
            return True

        except Exception as e:
            logger.error(f"訂閱商品 {symbol} 失敗: {e}")
            return False

    def unsubscribe(self, symbol: str) -> bool:
        """
        取消訂閱商品報價

        減少訂閱者計數，當計數歸零時取消 Shioaji 訂閱。

        Args:
            symbol: 商品代碼

        Returns:
            操作成功返回 True，失敗返回 False
        """
        try:
            # 檢查是否有訂閱
            if symbol not in self._subscriptions:
                logger.warning(f"商品 {symbol} 未訂閱，無法取消")
                return False

            # 減少計數
            current_count = self._subscriber_counts.get(symbol, 0)
            if current_count > 1:
                self._subscriber_counts[symbol] = current_count - 1
                logger.debug(
                    f"商品 {symbol} 減少訂閱計數至 "
                    f"{self._subscriber_counts[symbol]}"
                )
                return True

            # 最後一個訂閱者，取消 Shioaji 訂閱（Tick 和 BidAsk）
            contract = self._subscriptions[symbol]
            self._api.quote.unsubscribe(
                contract,
                quote_type=sj.constant.QuoteType.Tick,
            )
            self._api.quote.unsubscribe(
                contract,
                quote_type=sj.constant.QuoteType.BidAsk,
            )

            # 清理記錄
            del self._subscriptions[symbol]
            if symbol in self._subscriber_counts:
                del self._subscriber_counts[symbol]

            # 清理 code 對應
            code = getattr(contract, 'code', None)
            if code and code in self._code_to_symbol:
                del self._code_to_symbol[code]

            logger.info(f"已取消訂閱商品 {symbol}，目前訂閱數: {len(self._subscriptions)}")
            return True

        except Exception as e:
            logger.error(f"取消訂閱商品 {symbol} 失敗: {e}")
            return False

    def _handle_quote(self, exchange: Any, quote: Any) -> None:
        """
        處理 Shioaji 報價回調

        將報價資料轉換為統一格式並發布到 Redis Pub/Sub

        Args:
            exchange: 交易所資訊
            quote: Shioaji 報價物件
        """
        try:
            # 從 code 取得 symbol
            code = quote.code
            symbol = self._code_to_symbol.get(code, code)

            # 記錄收到的報價（使用 INFO 級別以便調試）
            logger.info(
                f"[_handle_quote] 處理報價: code={code}, symbol={symbol}, "
                f"映射表={list(self._code_to_symbol.keys())}"
            )

            # 解析報價資料
            # Shioaji v1 quote 格式: close, buy_price, sell_price 是 list
            close_price = quote.close[0] if isinstance(quote.close, list) else quote.close
            buy_price = quote.buy_price[0] if isinstance(quote.buy_price, list) else getattr(quote, 'buy_price', 0)
            sell_price = quote.sell_price[0] if isinstance(quote.sell_price, list) else getattr(quote, 'sell_price', 0)

            # 取得時間戳
            ts = quote.datetime
            if isinstance(ts, datetime):
                timestamp = int(ts.timestamp() * 1000)
            else:
                timestamp = int(ts) if ts else 0

            # 建立報價資料物件
            quote_data = QuoteData(
                symbol=symbol,
                code=code,
                close=close_price,
                open=getattr(quote, 'open', 0.0),
                high=getattr(quote, 'high', 0.0),
                low=getattr(quote, 'low', 0.0),
                change_price=getattr(quote, 'change_price', 0.0),
                change_rate=getattr(quote, 'change_rate', 0.0),
                volume=getattr(quote, 'volume', 0),
                total_volume=getattr(quote, 'total_volume', 0),
                buy_price=buy_price,
                sell_price=sell_price,
                buy_volume=getattr(quote, 'buy_volume', 0),
                sell_volume=getattr(quote, 'sell_volume', 0),
                timestamp=timestamp,
            )

            # 發布到 Redis Pub/Sub
            channel = f"{QUOTE_CHANNEL_PREFIX}{symbol}"
            self._redis.publish(channel, quote_data.to_json())

            logger.info(f"已發布報價到 {channel}: close={close_price}")

        except Exception as e:
            logger.error(f"處理報價回調失敗: {e}")

    def _try_create_dynamic_mapping(self, code: str) -> Optional[str]:
        """
        嘗試為未知的合約代碼建立動態映射

        當訂閱別名合約（如 TMFR1）時，Shioaji 返回的報價 code 是實際合約代碼
        （如 TMFB6），需要動態建立映射。

        Args:
            code: 報價的合約代碼（如 TMFB6）

        Returns:
            映射到的 symbol，如果無法映射則返回 None
        """
        # 檢查是否有訂閱的別名合約可能對應這個 code
        for subscribed_symbol, contract in self._subscriptions.items():
            # 檢查是否是別名合約（R1=近月, R2=次月）
            if subscribed_symbol.endswith('R1') or subscribed_symbol.endswith('R2'):
                # 獲取合約的基礎代碼（如 TMF, MXF, TXF）
                base_code = subscribed_symbol[:-2]  # 移除 R1/R2

                # 檢查報價的 code 是否屬於同一商品類型
                # 期貨代碼格式: TMF{月份代碼}{年份} 如 TMFB6
                # 比較前 3 個字元（如 TMF, MXF, TXF）
                if len(code) >= 3 and len(base_code) >= 3 and code[:3] == base_code[:3]:
                    # 建立動態映射
                    self._code_to_symbol[code] = subscribed_symbol
                    logger.info(
                        f"[動態映射] 建立別名映射: {code} -> {subscribed_symbol}, "
                        f"目前映射表: {self._code_to_symbol}"
                    )
                    return subscribed_symbol

        return None

    def _handle_tick_fop(self, exchange: Exchange, tick: TickFOPv1) -> None:
        """
        處理期貨/選擇權 Tick 報價回調

        將 TickFOPv1 資料轉換為統一格式並發布到 Redis Pub/Sub

        Args:
            exchange: 交易所資訊
            tick: Shioaji TickFOPv1 物件
        """
        try:
            code = tick.code

            # 嘗試從映射表獲取 symbol
            symbol = self._code_to_symbol.get(code)

            # 如果 code 不在映射表中，嘗試動態建立映射
            # 這處理別名合約的情況（如 TMFR1 -> TMFB6）
            if symbol is None:
                symbol = self._try_create_dynamic_mapping(code)
                if symbol is None:
                    symbol = code  # 如果仍無法映射，使用 code 作為 symbol

            logger.info(
                f"[_handle_tick_fop] 處理報價: code={code}, symbol={symbol}, "
                f"close={tick.close}, 映射表={list(self._code_to_symbol.keys())}"
            )

            # 取得時間戳
            ts = tick.datetime
            if isinstance(ts, datetime):
                timestamp = int(ts.timestamp() * 1000)
            else:
                timestamp = int(ts) if ts else 0

            # 建立報價資料物件
            quote_data = QuoteData(
                symbol=symbol,
                code=code,
                quote_type="tick",
                close=float(tick.close) if tick.close else 0.0,
                open=float(tick.open) if tick.open else 0.0,
                high=float(tick.high) if tick.high else 0.0,
                low=float(tick.low) if tick.low else 0.0,
                change_price=float(tick.price_chg) if hasattr(tick, 'price_chg') and tick.price_chg else 0.0,
                change_rate=float(tick.pct_chg) if hasattr(tick, 'pct_chg') and tick.pct_chg else 0.0,
                volume=int(tick.volume) if tick.volume else 0,
                total_volume=int(tick.total_volume) if tick.total_volume else 0,
                buy_price=0.0,  # Tick 資料不包含五檔
                sell_price=0.0,
                buy_volume=int(tick.bid_side_total_vol) if hasattr(tick, 'bid_side_total_vol') and tick.bid_side_total_vol else 0,
                sell_volume=int(tick.ask_side_total_vol) if hasattr(tick, 'ask_side_total_vol') and tick.ask_side_total_vol else 0,
                timestamp=timestamp,
            )

            # 發布到 Redis Pub/Sub
            channel = f"{QUOTE_CHANNEL_PREFIX}{symbol}"
            self._redis.publish(channel, quote_data.to_json())

            logger.info(f"已發布報價到 {channel}: close={tick.close}")

        except Exception as e:
            logger.error(f"處理期貨 Tick 回調失敗: {e}", exc_info=True)

    def _handle_bidask_fop(self, exchange: Exchange, bidask: BidAskFOPv1) -> None:
        """
        處理期貨/選擇權 BidAsk 報價回調

        將 BidAskFOPv1 資料轉換為統一格式並發布到 Redis Pub/Sub

        Args:
            exchange: 交易所資訊
            bidask: Shioaji BidAskFOPv1 物件
        """
        try:
            code = bidask.code

            # 嘗試從映射表獲取 symbol
            symbol = self._code_to_symbol.get(code)

            # 如果 code 不在映射表中，嘗試動態建立映射
            if symbol is None:
                symbol = self._try_create_dynamic_mapping(code)
                if symbol is None:
                    symbol = code

            # BidAsk 資料較頻繁，使用 debug 級別
            logger.debug(
                f"[_handle_bidask_fop] 處理五檔: code={code}, symbol={symbol}"
            )

            # 取得時間戳
            ts = bidask.datetime
            if isinstance(ts, datetime):
                timestamp = int(ts.timestamp() * 1000)
            else:
                timestamp = int(ts) if ts else 0

            # 取得最佳買賣價
            bid_price = float(bidask.bid_price[0]) if bidask.bid_price else 0.0
            ask_price = float(bidask.ask_price[0]) if bidask.ask_price else 0.0
            bid_volume = int(bidask.bid_volume[0]) if bidask.bid_volume else 0
            ask_volume = int(bidask.ask_volume[0]) if bidask.ask_volume else 0

            # 建立報價資料物件（五檔資料主要更新買賣價量）
            quote_data = QuoteData(
                symbol=symbol,
                code=code,
                quote_type="bidask",
                close=0.0,  # BidAsk 不包含成交價
                open=0.0,
                high=0.0,
                low=0.0,
                change_price=0.0,
                change_rate=0.0,
                volume=0,
                total_volume=0,
                buy_price=bid_price,
                sell_price=ask_price,
                buy_volume=bid_volume,
                sell_volume=ask_volume,
                timestamp=timestamp,
            )

            # 發布到 Redis Pub/Sub（與 Tick 使用相同 channel，前端透過 quote_type 區分）
            channel = f"{QUOTE_CHANNEL_PREFIX}{symbol}"
            self._redis.publish(channel, quote_data.to_json())

        except Exception as e:
            logger.error(f"處理期貨 BidAsk 回調失敗: {e}", exc_info=True)

    def _handle_quote_v2(self, topic: str, quote: dict) -> None:
        """
        處理 Shioaji 報價回調（v2 格式，使用 set_quote_callback）

        將報價資料轉換為統一格式並發布到 Redis Pub/Sub

        Args:
            topic: 報價主題（包含合約代碼）
            quote: Shioaji 報價字典
        """
        try:
            # 從 topic 或 quote 中取得 code
            # topic 格式可能是: "Q/TFE/TMFC6" 或類似
            code = quote.get('code', '')
            if not code and '/' in topic:
                code = topic.split('/')[-1]

            symbol = self._code_to_symbol.get(code, code)

            # 記錄收到的報價
            logger.info(
                f"[_handle_quote_v2] 處理報價: topic={topic}, code={code}, "
                f"symbol={symbol}, 映射表={list(self._code_to_symbol.keys())}"
            )

            # 解析報價資料（字典格式）
            close_price = quote.get('close', 0.0)
            if isinstance(close_price, list):
                close_price = close_price[0] if close_price else 0.0

            buy_price = quote.get('bid_price', [0.0])
            if isinstance(buy_price, list):
                buy_price = buy_price[0] if buy_price else 0.0

            sell_price = quote.get('ask_price', [0.0])
            if isinstance(sell_price, list):
                sell_price = sell_price[0] if sell_price else 0.0

            buy_volume = quote.get('bid_volume', [0])
            if isinstance(buy_volume, list):
                buy_volume = buy_volume[0] if buy_volume else 0

            sell_volume = quote.get('ask_volume', [0])
            if isinstance(sell_volume, list):
                sell_volume = sell_volume[0] if sell_volume else 0

            # 取得時間戳
            ts = quote.get('datetime')
            if isinstance(ts, datetime):
                timestamp = int(ts.timestamp() * 1000)
            elif ts:
                timestamp = int(ts)
            else:
                timestamp = 0

            # 建立報價資料物件
            quote_data = QuoteData(
                symbol=symbol,
                code=code,
                close=float(close_price) if close_price else 0.0,
                open=float(quote.get('open', 0.0) or 0.0),
                high=float(quote.get('high', 0.0) or 0.0),
                low=float(quote.get('low', 0.0) or 0.0),
                change_price=float(quote.get('price_chg', 0.0) or 0.0),
                change_rate=float(quote.get('pct_chg', 0.0) or 0.0),
                volume=int(quote.get('volume', 0) or 0),
                total_volume=int(quote.get('total_volume', 0) or 0),
                buy_price=float(buy_price) if buy_price else 0.0,
                sell_price=float(sell_price) if sell_price else 0.0,
                buy_volume=int(buy_volume) if buy_volume else 0,
                sell_volume=int(sell_volume) if sell_volume else 0,
                timestamp=timestamp,
            )

            # 發布到 Redis Pub/Sub
            channel = f"{QUOTE_CHANNEL_PREFIX}{symbol}"
            self._redis.publish(channel, quote_data.to_json())

            logger.info(f"已發布報價到 {channel}: close={close_price}")

        except Exception as e:
            logger.error(f"處理報價回調失敗 (v2): {e}", exc_info=True)

    def get_subscriptions(self) -> List[str]:
        """
        取得目前訂閱的商品列表

        Returns:
            訂閱的商品代碼列表
        """
        return list(self._subscriptions.keys())

    def get_subscriber_count(self, symbol: str) -> int:
        """
        取得特定商品的訂閱者數量

        Args:
            symbol: 商品代碼

        Returns:
            訂閱者數量
        """
        return self._subscriber_counts.get(symbol, 0)

    def is_subscribed(self, symbol: str) -> bool:
        """
        檢查商品是否已訂閱

        Args:
            symbol: 商品代碼

        Returns:
            已訂閱返回 True
        """
        return symbol in self._subscriptions

    def cleanup(self) -> None:
        """
        清理所有訂閱

        在 Worker 關閉時呼叫，取消所有 Shioaji 訂閱
        """
        logger.info(f"開始清理訂閱，目前訂閱數: {len(self._subscriptions)}")

        for symbol, contract in list(self._subscriptions.items()):
            try:
                self._api.quote.unsubscribe(contract)
                logger.debug(f"已取消訂閱 {symbol}")
            except Exception as e:
                logger.error(f"取消訂閱 {symbol} 失敗: {e}")

        self._subscriptions.clear()
        self._subscriber_counts.clear()
        self._code_to_symbol.clear()

        logger.info("訂閱清理完成")

"""
QuoteManager - 即時報價訂閱管理器

負責管理 Shioaji 即時報價訂閱，並透過 Redis Pub/Sub 發布報價更新。

功能：
- 訂閱/取消訂閱 Shioaji 即時報價
- 處理 Shioaji on_quote 回調
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

        在 Worker 初始化時呼叫，註冊 on_quote 回調
        """
        @self._api.quote.on_quote
        def on_quote(exchange, quote):
            self._handle_quote(exchange, quote)

        logger.info("已設置 Shioaji on_quote 回調")

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
            self._api.quote.subscribe(
                contract,
                quote_type=sj.constant.QuoteType.Quote,
                version=sj.constant.QuoteVersion.v1,
            )

            # 記錄訂閱
            self._subscriptions[symbol] = contract
            self._subscriber_counts[symbol] = 1

            # 建立 code 到 symbol 的對應
            if hasattr(contract, 'code'):
                self._code_to_symbol[contract.code] = symbol

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

            # 最後一個訂閱者，取消 Shioaji 訂閱
            contract = self._subscriptions[symbol]
            self._api.quote.unsubscribe(contract)

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

            logger.debug(f"已發布報價 {symbol}: {close_price}")

        except Exception as e:
            logger.error(f"處理報價回調失敗: {e}")

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

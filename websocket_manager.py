"""
WebSocketManager - WebSocket 連線管理器

管理前端 WebSocket 連線，監聽 Redis Pub/Sub 並廣播報價更新。

功能：
- WebSocket 連線生命週期管理
- 訂閱/取消訂閱報價
- 監聽 Redis Pub/Sub 報價頻道
- 廣播報價給訂閱的客戶端
"""
import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Any

from fastapi import WebSocket
import redis.asyncio as aioredis

from quote_manager import QUOTE_CHANNEL_PREFIX

logger = logging.getLogger(__name__)


@dataclass
class ConnectionInfo:
    """
    WebSocket 連線資訊

    追蹤每個連線的 WebSocket 實例和訂閱的商品
    """
    websocket: WebSocket
    client_id: str
    subscribed_symbols: Set[str] = field(default_factory=set)


class WebSocketManager:
    """
    WebSocket 連線管理器

    負責管理所有 WebSocket 連線，並透過 Redis Pub/Sub 接收報價更新，
    廣播給訂閱的客戶端。

    使用方式：
    1. FastAPI 啟動時建立 WebSocketManager 實例
    2. 在 lifespan 中啟動 Redis 監聽任務
    3. WebSocket 端點使用 connect/disconnect 管理連線
    4. 客戶端透過 subscribe_symbol/unsubscribe_symbol 訂閱報價
    """

    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        """
        初始化 WebSocketManager

        Args:
            redis_client: 異步 Redis 客戶端（可選，稍後設定）
        """
        self._redis: Optional[aioredis.Redis] = redis_client

        # 連線管理 {client_id: ConnectionInfo}
        self._connections: Dict[str, ConnectionInfo] = {}

        # 商品訂閱關係 {symbol: set(client_ids)}
        self._symbol_subscribers: Dict[str, Set[str]] = {}

        # 背景任務
        self._pubsub_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info("WebSocketManager 初始化完成")

    def set_redis_client(self, redis_client: aioredis.Redis) -> None:
        """設定 Redis 客戶端"""
        self._redis = redis_client

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """
        處理新的 WebSocket 連線

        Args:
            websocket: FastAPI WebSocket 實例
            client_id: 客戶端唯一識別碼
        """
        # 如果已存在相同 client_id 的連線，先斷開舊連線
        if client_id in self._connections:
            logger.info(f"客戶端 {client_id} 重新連線，關閉舊連線")
            await self._cleanup_connection(client_id)

        # 建立新連線
        self._connections[client_id] = ConnectionInfo(
            websocket=websocket,
            client_id=client_id,
        )

        logger.info(f"客戶端 {client_id} 已連線，目前連線數: {len(self._connections)}")

    async def disconnect(self, client_id: str) -> None:
        """
        處理 WebSocket 斷線

        Args:
            client_id: 客戶端唯一識別碼
        """
        await self._cleanup_connection(client_id)
        logger.info(f"客戶端 {client_id} 已斷線，目前連線數: {len(self._connections)}")

    async def _cleanup_connection(self, client_id: str) -> None:
        """
        清理連線相關資源

        Args:
            client_id: 客戶端唯一識別碼
        """
        if client_id not in self._connections:
            return

        conn_info = self._connections[client_id]

        # 清理訂閱關係
        for symbol in list(conn_info.subscribed_symbols):
            if symbol in self._symbol_subscribers:
                self._symbol_subscribers[symbol].discard(client_id)
                # 如果沒有訂閱者了，清理該 symbol
                if not self._symbol_subscribers[symbol]:
                    del self._symbol_subscribers[symbol]

        # 移除連線
        del self._connections[client_id]

    async def subscribe_symbol(self, client_id: str, symbol: str) -> bool:
        """
        客戶端訂閱商品報價

        Args:
            client_id: 客戶端唯一識別碼
            symbol: 商品代碼

        Returns:
            訂閱成功返回 True
        """
        if client_id not in self._connections:
            logger.warning(f"客戶端 {client_id} 未連線，無法訂閱")
            return False

        conn_info = self._connections[client_id]
        conn_info.subscribed_symbols.add(symbol)

        if symbol not in self._symbol_subscribers:
            self._symbol_subscribers[symbol] = set()
        self._symbol_subscribers[symbol].add(client_id)

        logger.debug(
            f"客戶端 {client_id} 訂閱 {symbol}，"
            f"該商品目前 {len(self._symbol_subscribers[symbol])} 個訂閱者"
        )
        return True

    async def unsubscribe_symbol(self, client_id: str, symbol: str) -> bool:
        """
        客戶端取消訂閱商品報價

        Args:
            client_id: 客戶端唯一識別碼
            symbol: 商品代碼

        Returns:
            取消成功返回 True
        """
        if client_id not in self._connections:
            return False

        conn_info = self._connections[client_id]
        conn_info.subscribed_symbols.discard(symbol)

        if symbol in self._symbol_subscribers:
            self._symbol_subscribers[symbol].discard(client_id)
            if not self._symbol_subscribers[symbol]:
                del self._symbol_subscribers[symbol]

        logger.debug(f"客戶端 {client_id} 取消訂閱 {symbol}")
        return True

    async def broadcast_to_symbol(self, symbol: str, message: Dict[str, Any]) -> None:
        """
        廣播訊息給訂閱特定商品的所有客戶端

        Args:
            symbol: 商品代碼
            message: 要發送的訊息
        """
        if symbol not in self._symbol_subscribers:
            return

        # 複製 set 避免迭代時修改
        subscribers = list(self._symbol_subscribers[symbol])
        failed_clients = []

        for client_id in subscribers:
            if client_id not in self._connections:
                failed_clients.append(client_id)
                continue

            try:
                websocket = self._connections[client_id].websocket
                await websocket.send_json(message)
            except Exception as e:
                logger.debug(f"發送訊息給 {client_id} 失敗: {e}")
                failed_clients.append(client_id)

        # 清理失敗的連線
        for client_id in failed_clients:
            await self._cleanup_connection(client_id)

    async def broadcast_all(self, message: Dict[str, Any]) -> None:
        """
        廣播訊息給所有連線的客戶端

        Args:
            message: 要發送的訊息
        """
        failed_clients = []

        for client_id, conn_info in list(self._connections.items()):
            try:
                await conn_info.websocket.send_json(message)
            except Exception as e:
                logger.debug(f"發送訊息給 {client_id} 失敗: {e}")
                failed_clients.append(client_id)

        # 清理失敗的連線
        for client_id in failed_clients:
            await self._cleanup_connection(client_id)

    async def _handle_redis_message(self, channel: str, data: str) -> None:
        """
        處理 Redis Pub/Sub 訊息

        Args:
            channel: Redis 頻道名稱
            data: 訊息資料（JSON 字串）
        """
        try:
            # 解析 channel 取得 symbol
            if not channel.startswith(QUOTE_CHANNEL_PREFIX):
                return

            symbol = channel[len(QUOTE_CHANNEL_PREFIX):]

            # 解析報價資料
            quote_data = json.loads(data)

            # 建立 WebSocket 訊息格式
            message = {
                "type": "quote",
                "symbol": symbol,
                "data": quote_data,
                "timestamp": quote_data.get("timestamp"),
            }

            # 廣播給訂閱者
            await self.broadcast_to_symbol(symbol, message)

        except json.JSONDecodeError as e:
            logger.error(f"解析 Redis 訊息失敗: {e}")
        except Exception as e:
            logger.error(f"處理 Redis 訊息失敗: {e}")

    async def start_pubsub_listener(self) -> None:
        """
        啟動 Redis Pub/Sub 監聽

        在 FastAPI lifespan 中呼叫，開始監聽報價更新
        """
        if self._redis is None:
            logger.error("Redis 客戶端未設定，無法啟動 Pub/Sub 監聽")
            return

        self._running = True
        pubsub = self._redis.pubsub()

        # 訂閱所有報價頻道
        pattern = f"{QUOTE_CHANNEL_PREFIX}*"
        await pubsub.psubscribe(pattern)

        logger.info(f"開始監聽 Redis Pub/Sub pattern: {pattern}")

        try:
            while self._running:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )

                if message is not None:
                    channel = message.get("channel")
                    data = message.get("data")

                    if channel and data:
                        # channel 和 data 可能是 bytes
                        if isinstance(channel, bytes):
                            channel = channel.decode("utf-8")
                        if isinstance(data, bytes):
                            data = data.decode("utf-8")

                        await self._handle_redis_message(channel, data)

                # 短暫休眠避免 CPU 佔用過高
                await asyncio.sleep(0.01)

        except asyncio.CancelledError:
            logger.info("Redis Pub/Sub 監聽被取消")
        except Exception as e:
            logger.error(f"Redis Pub/Sub 監聽錯誤: {e}")
        finally:
            await pubsub.punsubscribe(pattern)
            await pubsub.close()
            logger.info("Redis Pub/Sub 監聽已停止")

    async def stop_pubsub_listener(self) -> None:
        """停止 Redis Pub/Sub 監聽"""
        self._running = False

        if self._pubsub_task:
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass

    def get_connection_count(self) -> int:
        """取得目前連線數量"""
        return len(self._connections)

    def get_symbol_subscriber_count(self, symbol: str) -> int:
        """取得特定商品的訂閱者數量"""
        return len(self._symbol_subscribers.get(symbol, set()))

    def get_all_subscribed_symbols(self) -> Set[str]:
        """取得所有有訂閱者的商品"""
        return set(self._symbol_subscribers.keys())

    def get_client_subscriptions(self, client_id: str) -> Set[str]:
        """取得特定客戶端訂閱的商品"""
        if client_id not in self._connections:
            return set()
        return self._connections[client_id].subscribed_symbols.copy()

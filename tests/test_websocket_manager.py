"""
WebSocketManager 單元測試

測試涵蓋：
1. WebSocket 連線管理
2. Redis Pub/Sub 監聽
3. 報價廣播功能
4. 訂閱/取消訂閱
5. 錯誤處理
"""
import json
import asyncio
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock, patch
from datetime import datetime

from websocket_manager import (
    WebSocketManager,
    ConnectionInfo,
)


class TestConnectionInfo:
    """ConnectionInfo 資料類測試"""

    def test_初始化應該設置正確的屬性(self):
        """測試: ConnectionInfo 應該正確初始化所有屬性"""
        # Arrange
        mock_websocket = Mock()

        # Act
        conn = ConnectionInfo(
            websocket=mock_websocket,
            client_id="client-123",
            subscribed_symbols={"MXF202601", "TXF202601"},
        )

        # Assert
        assert conn.websocket is mock_websocket
        assert conn.client_id == "client-123"
        assert "MXF202601" in conn.subscribed_symbols
        assert "TXF202601" in conn.subscribed_symbols


class TestWebSocketManagerInit:
    """WebSocketManager 初始化測試"""

    def test_初始化應該建立空的連線字典(self):
        """測試: 初始化時應該建立空的連線追蹤字典"""
        # Arrange & Act
        manager = WebSocketManager()

        # Assert
        assert manager._connections == {}
        assert manager._symbol_subscribers == {}

    @pytest.mark.asyncio
    async def test_初始化應該可以設定Redis客戶端(self):
        """測試: 初始化時應該可以設定 Redis 客戶端"""
        # Arrange
        mock_redis = Mock()

        # Act
        manager = WebSocketManager(redis_client=mock_redis)

        # Assert
        assert manager._redis is mock_redis


class TestWebSocketManagerConnect:
    """WebSocketManager 連線管理測試"""

    @pytest.mark.asyncio
    async def test_connect_應該註冊新連線(self):
        """測試: connect 應該將新連線加入管理"""
        # Arrange
        manager = WebSocketManager()
        mock_websocket = AsyncMock()
        client_id = "test-client-1"

        # Act
        await manager.connect(mock_websocket, client_id)

        # Assert
        assert client_id in manager._connections
        assert manager._connections[client_id].websocket is mock_websocket

    @pytest.mark.asyncio
    async def test_connect_重複連線應該更新現有連線(self):
        """測試: 同一 client_id 重複連線應該更新現有連線"""
        # Arrange
        manager = WebSocketManager()
        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        client_id = "test-client-1"

        # Act
        await manager.connect(mock_ws1, client_id)
        await manager.connect(mock_ws2, client_id)

        # Assert
        assert manager._connections[client_id].websocket is mock_ws2


class TestWebSocketManagerDisconnect:
    """WebSocketManager 斷線處理測試"""

    @pytest.mark.asyncio
    async def test_disconnect_應該移除連線(self):
        """測試: disconnect 應該從管理器移除連線"""
        # Arrange
        manager = WebSocketManager()
        mock_websocket = AsyncMock()
        client_id = "test-client-1"
        await manager.connect(mock_websocket, client_id)

        # Act
        await manager.disconnect(client_id)

        # Assert
        assert client_id not in manager._connections

    @pytest.mark.asyncio
    async def test_disconnect_應該清理訂閱關係(self):
        """測試: disconnect 應該清理該連線的所有訂閱關係"""
        # Arrange
        manager = WebSocketManager()
        mock_websocket = AsyncMock()
        client_id = "test-client-1"
        await manager.connect(mock_websocket, client_id)
        await manager.subscribe_symbol(client_id, "MXF202601")

        # Act
        await manager.disconnect(client_id)

        # Assert
        assert client_id not in manager._symbol_subscribers.get("MXF202601", set())

    @pytest.mark.asyncio
    async def test_disconnect_不存在的連線應該不報錯(self):
        """測試: 斷開不存在的連線應該不拋出例外"""
        # Arrange
        manager = WebSocketManager()

        # Act & Assert - 應該不拋出例外
        await manager.disconnect("non-existent-client")


class TestWebSocketManagerSubscribe:
    """WebSocketManager 訂閱管理測試"""

    @pytest.mark.asyncio
    async def test_subscribe_symbol_應該建立訂閱關係(self):
        """測試: subscribe_symbol 應該建立 client 與 symbol 的訂閱關係"""
        # Arrange
        manager = WebSocketManager()
        mock_websocket = AsyncMock()
        client_id = "test-client-1"
        await manager.connect(mock_websocket, client_id)

        # Act
        result = await manager.subscribe_symbol(client_id, "MXF202601")

        # Assert
        assert result is True
        assert "MXF202601" in manager._connections[client_id].subscribed_symbols
        assert client_id in manager._symbol_subscribers["MXF202601"]

    @pytest.mark.asyncio
    async def test_subscribe_symbol_未連線client應該返回False(self):
        """測試: 未連線的 client 訂閱應該返回 False"""
        # Arrange
        manager = WebSocketManager()

        # Act
        result = await manager.subscribe_symbol("non-existent", "MXF202601")

        # Assert
        assert result is False

    @pytest.mark.asyncio
    async def test_unsubscribe_symbol_應該移除訂閱關係(self):
        """測試: unsubscribe_symbol 應該移除訂閱關係"""
        # Arrange
        manager = WebSocketManager()
        mock_websocket = AsyncMock()
        client_id = "test-client-1"
        await manager.connect(mock_websocket, client_id)
        await manager.subscribe_symbol(client_id, "MXF202601")

        # Act
        result = await manager.unsubscribe_symbol(client_id, "MXF202601")

        # Assert
        assert result is True
        assert "MXF202601" not in manager._connections[client_id].subscribed_symbols


class TestWebSocketManagerBroadcast:
    """WebSocketManager 廣播功能測試"""

    @pytest.mark.asyncio
    async def test_broadcast_to_symbol_應該發送給所有訂閱者(self):
        """測試: broadcast_to_symbol 應該發送訊息給所有訂閱該 symbol 的客戶端"""
        # Arrange
        manager = WebSocketManager()

        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws3 = AsyncMock()

        await manager.connect(mock_ws1, "client-1")
        await manager.connect(mock_ws2, "client-2")
        await manager.connect(mock_ws3, "client-3")

        await manager.subscribe_symbol("client-1", "MXF202601")
        await manager.subscribe_symbol("client-2", "MXF202601")
        # client-3 未訂閱

        message = {"type": "quote", "symbol": "MXF202601", "close": 21500.0}

        # Act
        await manager.broadcast_to_symbol("MXF202601", message)

        # Assert
        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)
        mock_ws3.send_json.assert_not_called()

    @pytest.mark.asyncio
    async def test_broadcast_to_symbol_發送失敗應該移除連線(self):
        """測試: 發送失敗的連線應該被移除"""
        # Arrange
        manager = WebSocketManager()

        mock_ws1 = AsyncMock()
        mock_ws1.send_json.side_effect = Exception("Connection closed")

        await manager.connect(mock_ws1, "client-1")
        await manager.subscribe_symbol("client-1", "MXF202601")

        message = {"type": "quote", "symbol": "MXF202601"}

        # Act
        await manager.broadcast_to_symbol("MXF202601", message)

        # Assert
        assert "client-1" not in manager._connections

    @pytest.mark.asyncio
    async def test_broadcast_all_應該發送給所有連線(self):
        """測試: broadcast_all 應該發送訊息給所有連線的客戶端"""
        # Arrange
        manager = WebSocketManager()

        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect(mock_ws1, "client-1")
        await manager.connect(mock_ws2, "client-2")

        message = {"type": "status", "message": "Server restarting"}

        # Act
        await manager.broadcast_all(message)

        # Assert
        mock_ws1.send_json.assert_called_once_with(message)
        mock_ws2.send_json.assert_called_once_with(message)


class TestWebSocketManagerStats:
    """WebSocketManager 統計資訊測試"""

    @pytest.mark.asyncio
    async def test_get_connection_count_應該返回連線數(self):
        """測試: get_connection_count 應該返回目前連線數量"""
        # Arrange
        manager = WebSocketManager()

        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect(mock_ws1, "client-1")
        await manager.connect(mock_ws2, "client-2")

        # Act
        count = manager.get_connection_count()

        # Assert
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_symbol_subscriber_count_應該返回訂閱者數量(self):
        """測試: get_symbol_subscriber_count 應該返回特定 symbol 的訂閱者數量"""
        # Arrange
        manager = WebSocketManager()

        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws3 = AsyncMock()

        await manager.connect(mock_ws1, "client-1")
        await manager.connect(mock_ws2, "client-2")
        await manager.connect(mock_ws3, "client-3")

        await manager.subscribe_symbol("client-1", "MXF202601")
        await manager.subscribe_symbol("client-2", "MXF202601")

        # Act
        count = manager.get_symbol_subscriber_count("MXF202601")

        # Assert
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_all_subscribed_symbols_應該返回所有訂閱的symbol(self):
        """測試: get_all_subscribed_symbols 應該返回所有有訂閱者的 symbol"""
        # Arrange
        manager = WebSocketManager()

        mock_ws1 = AsyncMock()

        await manager.connect(mock_ws1, "client-1")
        await manager.subscribe_symbol("client-1", "MXF202601")
        await manager.subscribe_symbol("client-1", "TXF202601")

        # Act
        symbols = manager.get_all_subscribed_symbols()

        # Assert
        assert "MXF202601" in symbols
        assert "TXF202601" in symbols


class TestWebSocketManagerPubSub:
    """WebSocketManager Redis Pub/Sub 監聽測試"""

    @pytest.mark.asyncio
    async def test_handle_redis_message_應該廣播報價(self):
        """測試: 收到 Redis 訊息時應該廣播給訂閱者"""
        # Arrange
        manager = WebSocketManager()

        mock_websocket = AsyncMock()
        await manager.connect(mock_websocket, "client-1")
        await manager.subscribe_symbol("client-1", "MXF202601")

        quote_data = {
            "symbol": "MXF202601",
            "close": 21500.0,
            "timestamp": 1704067200000,
        }

        # Act
        await manager._handle_redis_message("quote:MXF202601", json.dumps(quote_data))

        # Assert
        mock_websocket.send_json.assert_called_once()
        call_args = mock_websocket.send_json.call_args[0][0]
        assert call_args["type"] == "quote"
        assert call_args["data"]["close"] == 21500.0

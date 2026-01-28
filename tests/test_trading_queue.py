"""
TradingQueueClient 單元測試

測試涵蓋：
1. 初始化與連線檢查
2. submit_request 核心方法（成功、超時、連線錯誤）
3. check_worker_health 健康檢查
4. 各種交易操作方法的參數傳遞
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from dataclasses import asdict

from trading_queue import (
    TradingQueueClient,
    TradingRequest,
    TradingResponse,
    TradingOperation,
    REQUEST_QUEUE,
    RESPONSE_PREFIX,
    get_queue_client,
)


class TestTradingRequest:
    """TradingRequest 資料類測試"""

    def test_to_json_應該正確序列化(self):
        """測試: TradingRequest 應該能正確序列化為 JSON"""
        # Arrange
        request = TradingRequest(
            request_id="test-123",
            operation="get_symbols",
            simulation=True,
            params={"key": "value"},
        )

        # Act
        json_str = request.to_json()
        parsed = json.loads(json_str)

        # Assert
        assert parsed["request_id"] == "test-123"
        assert parsed["operation"] == "get_symbols"
        assert parsed["simulation"] is True
        assert parsed["params"] == {"key": "value"}

    def test_from_json_應該正確反序列化(self):
        """測試: TradingRequest 應該能從 JSON 正確反序列化"""
        # Arrange
        json_str = json.dumps({
            "request_id": "test-456",
            "operation": "ping",
            "simulation": False,
            "params": {},
        })

        # Act
        request = TradingRequest.from_json(json_str)

        # Assert
        assert request.request_id == "test-456"
        assert request.operation == "ping"
        assert request.simulation is False
        assert request.params == {}


class TestTradingResponse:
    """TradingResponse 資料類測試"""

    def test_to_json_成功回應應該正確序列化(self):
        """測試: 成功的 TradingResponse 應該能正確序列化"""
        # Arrange
        response = TradingResponse(
            request_id="test-123",
            success=True,
            data={"symbols": ["MXF", "TXF"]},
            error=None,
        )

        # Act
        json_str = response.to_json()
        parsed = json.loads(json_str)

        # Assert
        assert parsed["request_id"] == "test-123"
        assert parsed["success"] is True
        assert parsed["data"] == {"symbols": ["MXF", "TXF"]}
        assert parsed["error"] is None

    def test_to_json_失敗回應應該正確序列化(self):
        """測試: 失敗的 TradingResponse 應該能正確序列化"""
        # Arrange
        response = TradingResponse(
            request_id="test-789",
            success=False,
            data=None,
            error="Connection failed",
        )

        # Act
        json_str = response.to_json()
        parsed = json.loads(json_str)

        # Assert
        assert parsed["success"] is False
        assert parsed["error"] == "Connection failed"

    def test_from_json_應該正確反序列化(self):
        """測試: TradingResponse 應該能從 JSON 正確反序列化"""
        # Arrange
        json_str = json.dumps({
            "request_id": "test-abc",
            "success": True,
            "data": [1, 2, 3],
            "error": None,
        })

        # Act
        response = TradingResponse.from_json(json_str)

        # Assert
        assert response.request_id == "test-abc"
        assert response.success is True
        assert response.data == [1, 2, 3]


class TestTradingQueueClientInit:
    """TradingQueueClient 初始化測試"""

    @patch("trading_queue.redis.from_url")
    def test_初始化成功時應該建立連線(self, mock_from_url):
        """測試: 初始化成功時應該建立 Redis 連線"""
        # Arrange
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_from_url.return_value = mock_redis

        # Act
        client = TradingQueueClient(redis_url="redis://localhost:6379/0")

        # Assert
        mock_from_url.assert_called_once_with(
            "redis://localhost:6379/0", decode_responses=True
        )
        mock_redis.ping.assert_called_once()

    @patch("trading_queue.redis.from_url")
    def test_Redis連線失敗時應該拋出例外(self, mock_from_url):
        """測試: Redis 連線失敗時應該拋出 ConnectionError"""
        # Arrange
        import redis
        mock_redis = Mock()
        mock_redis.ping.side_effect = redis.ConnectionError("Connection refused")
        mock_from_url.return_value = mock_redis

        # Act & Assert
        with pytest.raises(redis.ConnectionError):
            TradingQueueClient(redis_url="redis://localhost:6379/0")


class TestTradingQueueClientSubmitRequest:
    """TradingQueueClient.submit_request 測試"""

    @patch("trading_queue.redis.from_url")
    def test_submit_request_成功時應該返回回應(self, mock_from_url):
        """測試: submit_request 成功時應該返回 TradingResponse"""
        # Arrange
        mock_redis = Mock()
        mock_redis.ping.return_value = True

        # 模擬成功的回應
        expected_response = TradingResponse(
            request_id="mock-uuid",
            success=True,
            data={"symbols": ["MXF"]},
        )
        mock_redis.blpop.return_value = ("key", expected_response.to_json())
        mock_from_url.return_value = mock_redis

        client = TradingQueueClient()

        # Act
        with patch("trading_queue.uuid.uuid4", return_value="mock-uuid"):
            response = client.submit_request(
                TradingOperation.GET_SYMBOLS,
                simulation=True,
            )

        # Assert
        assert response.success is True
        assert response.data == {"symbols": ["MXF"]}
        mock_redis.rpush.assert_called_once()

    @patch("trading_queue.redis.from_url")
    def test_submit_request_超時時應該拋出TimeoutError(self, mock_from_url):
        """測試: submit_request 超時時應該拋出 TimeoutError"""
        # Arrange
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.blpop.return_value = None  # 超時返回 None
        mock_from_url.return_value = mock_redis

        client = TradingQueueClient()

        # Act & Assert
        with pytest.raises(TimeoutError, match="Trading request timed out"):
            client.submit_request(
                TradingOperation.PING,
                simulation=True,
                timeout=1,
            )

    @patch("trading_queue.redis.from_url")
    def test_submit_request_連線錯誤時應該拋出ConnectionError(self, mock_from_url):
        """測試: submit_request 連線錯誤時應該拋出 ConnectionError"""
        # Arrange
        import redis as redis_lib
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.rpush.side_effect = redis_lib.ConnectionError("Connection lost")
        mock_from_url.return_value = mock_redis

        client = TradingQueueClient()

        # Act & Assert
        with pytest.raises(ConnectionError, match="Failed to communicate"):
            client.submit_request(TradingOperation.PING, simulation=True)

    @patch("trading_queue.redis.from_url")
    def test_submit_request_應該正確傳遞參數(self, mock_from_url):
        """測試: submit_request 應該正確將參數傳遞到 Redis 隊列"""
        # Arrange
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.blpop.return_value = (
            "key",
            TradingResponse(request_id="test", success=True).to_json(),
        )
        mock_from_url.return_value = mock_redis

        client = TradingQueueClient()

        # Act
        with patch("trading_queue.uuid.uuid4", return_value="fixed-uuid"):
            client.submit_request(
                TradingOperation.GET_SYMBOL_INFO,
                simulation=False,
                params={"symbol": "MXFJ5"},
            )

        # Assert
        # 驗證 rpush 被調用，並檢查請求內容
        rpush_call = mock_redis.rpush.call_args
        assert rpush_call[0][0] == REQUEST_QUEUE

        request_json = rpush_call[0][1]
        request_data = json.loads(request_json)
        assert request_data["operation"] == "get_symbol_info"
        assert request_data["simulation"] is False
        assert request_data["params"]["symbol"] == "MXFJ5"


class TestTradingQueueClientHealthCheck:
    """TradingQueueClient.check_worker_health 測試"""

    @patch("trading_queue.redis.from_url")
    def test_check_worker_health_Worker健康時應該返回True(self, mock_from_url):
        """測試: Worker 健康時 check_worker_health 應該返回 True"""
        # Arrange
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.blpop.return_value = (
            "key",
            TradingResponse(request_id="test", success=True).to_json(),
        )
        mock_from_url.return_value = mock_redis

        client = TradingQueueClient()

        # Act
        result = client.check_worker_health()

        # Assert
        assert result is True

    @patch("trading_queue.redis.from_url")
    def test_check_worker_health_超時時應該返回False(self, mock_from_url):
        """測試: Worker 超時時 check_worker_health 應該返回 False"""
        # Arrange
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.blpop.return_value = None  # 超時
        mock_from_url.return_value = mock_redis

        client = TradingQueueClient()

        # Act
        result = client.check_worker_health()

        # Assert
        assert result is False

    @patch("trading_queue.redis.from_url")
    def test_check_worker_health_連線錯誤時應該返回False(self, mock_from_url):
        """測試: 連線錯誤時 check_worker_health 應該返回 False"""
        # Arrange
        import redis as redis_lib
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.rpush.side_effect = redis_lib.ConnectionError("Connection lost")
        mock_from_url.return_value = mock_redis

        client = TradingQueueClient()

        # Act
        result = client.check_worker_health()

        # Assert
        assert result is False


class TestTradingQueueClientOperations:
    """TradingQueueClient 各種操作方法測試"""

    @patch("trading_queue.redis.from_url")
    def setup_method(self, method, mock_from_url=None):
        """每個測試前的準備工作"""
        # 這個方法會在每個測試方法前被調用
        pass

    def _create_mock_client(self, mock_from_url):
        """建立 Mock 客戶端的輔助方法"""
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_redis.blpop.return_value = (
            "key",
            TradingResponse(request_id="test", success=True, data={}).to_json(),
        )
        mock_from_url.return_value = mock_redis
        return TradingQueueClient(), mock_redis

    @patch("trading_queue.redis.from_url")
    def test_get_symbols_應該調用正確的操作(self, mock_from_url):
        """測試: get_symbols 應該使用 GET_SYMBOLS 操作"""
        # Arrange
        client, mock_redis = self._create_mock_client(mock_from_url)

        # Act
        client.get_symbols(simulation=True)

        # Assert
        request_json = mock_redis.rpush.call_args[0][1]
        request_data = json.loads(request_json)
        assert request_data["operation"] == TradingOperation.GET_SYMBOLS.value

    @patch("trading_queue.redis.from_url")
    def test_get_symbol_info_應該傳遞symbol參數(self, mock_from_url):
        """測試: get_symbol_info 應該正確傳遞 symbol 參數"""
        # Arrange
        client, mock_redis = self._create_mock_client(mock_from_url)

        # Act
        client.get_symbol_info(symbol="TXFJ5", simulation=False)

        # Assert
        request_json = mock_redis.rpush.call_args[0][1]
        request_data = json.loads(request_json)
        assert request_data["operation"] == TradingOperation.GET_SYMBOL_INFO.value
        assert request_data["params"]["symbol"] == "TXFJ5"
        assert request_data["simulation"] is False

    @patch("trading_queue.redis.from_url")
    def test_place_entry_order_應該傳遞所有必要參數(self, mock_from_url):
        """測試: place_entry_order 應該正確傳遞所有交易參數"""
        # Arrange
        client, mock_redis = self._create_mock_client(mock_from_url)

        # Act
        client.place_entry_order(
            symbol="MXFJ5",
            quantity=1,
            action="Buy",
            simulation=True,
            price_type="LMT",
            price=21000.0,
        )

        # Assert
        request_json = mock_redis.rpush.call_args[0][1]
        request_data = json.loads(request_json)
        assert request_data["operation"] == TradingOperation.PLACE_ENTRY_ORDER.value
        assert request_data["params"]["symbol"] == "MXFJ5"
        assert request_data["params"]["quantity"] == 1
        assert request_data["params"]["action"] == "Buy"
        assert request_data["params"]["price_type"] == "LMT"
        assert request_data["params"]["price"] == 21000.0

    @patch("trading_queue.redis.from_url")
    def test_place_entry_order_市價單不應該包含price(self, mock_from_url):
        """測試: 市價單的 place_entry_order 不應該包含 price 參數"""
        # Arrange
        client, mock_redis = self._create_mock_client(mock_from_url)

        # Act
        client.place_entry_order(
            symbol="MXFJ5",
            quantity=1,
            action="Buy",
            simulation=True,
            price_type="MKT",
            price=None,
        )

        # Assert
        request_json = mock_redis.rpush.call_args[0][1]
        request_data = json.loads(request_json)
        assert "price" not in request_data["params"]
        assert request_data["params"]["price_type"] == "MKT"

    @patch("trading_queue.redis.from_url")
    def test_place_exit_order_應該傳遞所有必要參數(self, mock_from_url):
        """測試: place_exit_order 應該正確傳遞平倉參數"""
        # Arrange
        client, mock_redis = self._create_mock_client(mock_from_url)

        # Act
        client.place_exit_order(
            symbol="MXFJ5",
            position_direction="Buy",
            simulation=True,
            price_type="LMT",
            price=21500.0,
        )

        # Assert
        request_json = mock_redis.rpush.call_args[0][1]
        request_data = json.loads(request_json)
        assert request_data["operation"] == TradingOperation.PLACE_EXIT_ORDER.value
        assert request_data["params"]["symbol"] == "MXFJ5"
        assert request_data["params"]["position_direction"] == "Buy"
        assert request_data["params"]["price_type"] == "LMT"
        assert request_data["params"]["price"] == 21500.0

    @patch("trading_queue.redis.from_url")
    def test_check_order_status_應該使用較長的超時時間(self, mock_from_url):
        """測試: check_order_status 應該使用 60 秒超時"""
        # Arrange
        client, mock_redis = self._create_mock_client(mock_from_url)

        # Act
        client.check_order_status(
            order_id="order-123",
            seqno="seq-456",
            simulation=True,
        )

        # Assert
        # 驗證 blpop 被調用時使用了 60 秒超時
        blpop_call = mock_redis.blpop.call_args
        assert blpop_call[1]["timeout"] == 60

    @patch("trading_queue.redis.from_url")
    def test_get_snapshot_應該傳遞symbol參數(self, mock_from_url):
        """測試: get_snapshot 應該正確傳遞 symbol 參數"""
        # Arrange
        client, mock_redis = self._create_mock_client(mock_from_url)

        # Act
        client.get_snapshot(symbol="MXFJ5", simulation=True)

        # Assert
        request_json = mock_redis.rpush.call_args[0][1]
        request_data = json.loads(request_json)
        assert request_data["operation"] == TradingOperation.GET_SNAPSHOT.value
        assert request_data["params"]["symbol"] == "MXFJ5"

    @patch("trading_queue.redis.from_url")
    def test_get_positions_應該調用正確的操作(self, mock_from_url):
        """測試: get_positions 應該使用 GET_POSITIONS 操作"""
        # Arrange
        client, mock_redis = self._create_mock_client(mock_from_url)

        # Act
        client.get_positions(simulation=False)

        # Assert
        request_json = mock_redis.rpush.call_args[0][1]
        request_data = json.loads(request_json)
        assert request_data["operation"] == TradingOperation.GET_POSITIONS.value
        assert request_data["simulation"] is False

    @patch("trading_queue.redis.from_url")
    def test_get_margin_應該調用正確的操作(self, mock_from_url):
        """測試: get_margin 應該使用 GET_MARGIN 操作"""
        # Arrange
        client, mock_redis = self._create_mock_client(mock_from_url)

        # Act
        client.get_margin(simulation=True)

        # Assert
        request_json = mock_redis.rpush.call_args[0][1]
        request_data = json.loads(request_json)
        assert request_data["operation"] == TradingOperation.GET_MARGIN.value

    @patch("trading_queue.redis.from_url")
    def test_list_trades_應該調用正確的操作(self, mock_from_url):
        """測試: list_trades 應該使用 LIST_TRADES 操作"""
        # Arrange
        client, mock_redis = self._create_mock_client(mock_from_url)

        # Act
        client.list_trades(simulation=True)

        # Assert
        request_json = mock_redis.rpush.call_args[0][1]
        request_data = json.loads(request_json)
        assert request_data["operation"] == TradingOperation.LIST_TRADES.value


class TestGetQueueClient:
    """get_queue_client 單例函數測試"""

    @patch("trading_queue._queue_client", None)
    @patch("trading_queue.redis.from_url")
    def test_get_queue_client_應該返回單例實例(self, mock_from_url):
        """測試: get_queue_client 應該返回同一個實例"""
        # Arrange
        mock_redis = Mock()
        mock_redis.ping.return_value = True
        mock_from_url.return_value = mock_redis

        # 重設模組狀態
        import trading_queue
        trading_queue._queue_client = None

        # Act
        client1 = get_queue_client()
        client2 = get_queue_client()

        # Assert
        assert client1 is client2
        # 應該只建立一次連線
        assert mock_from_url.call_count == 1

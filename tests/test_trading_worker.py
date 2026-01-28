"""
TradingWorker 單元測試

測試涵蓋：
1. TradingWorker 初始化
2. 信號處理
3. 請求處理邏輯 (_handle_request_inner)
4. 連線管理邏輯
"""
import pytest
from unittest.mock import Mock, MagicMock, patch, PropertyMock
import signal

from trading_queue import TradingRequest, TradingResponse, TradingOperation


class TestTradingWorkerInit:
    """TradingWorker 初始化測試"""

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_初始化應該建立Redis連線(self, mock_signal, mock_redis_from_url):
        """測試: 初始化應該建立 Redis 連線"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis = Mock()
        mock_redis_from_url.return_value = mock_redis

        # Act
        worker = TradingWorker()

        # Assert
        mock_redis_from_url.assert_called_once()
        assert worker.redis == mock_redis
        assert worker.running is False

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_初始化應該設定信號處理器(self, mock_signal, mock_redis_from_url):
        """測試: 初始化應該設定 SIGTERM 和 SIGINT 處理器"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        # Act
        worker = TradingWorker()

        # Assert
        # 應該註冊 SIGTERM 和 SIGINT
        assert mock_signal.call_count == 2
        calls = [call[0][0] for call in mock_signal.call_args_list]
        assert signal.SIGTERM in calls
        assert signal.SIGINT in calls

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_初始化應該建立空的API客戶端字典(self, mock_signal, mock_redis_from_url):
        """測試: 初始化應該建立空的 API 客戶端字典"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        # Act
        worker = TradingWorker()

        # Assert
        assert worker.api_clients[True] is None  # simulation
        assert worker.api_clients[False] is None  # real


class TestSignalHandler:
    """信號處理測試"""

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_信號處理器應該設定running為False(self, mock_signal, mock_redis_from_url):
        """測試: 收到 SIGTERM/SIGINT 時應該設定 running 為 False"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()
        worker = TradingWorker()
        worker.running = True

        # Act
        worker._signal_handler(signal.SIGTERM, None)

        # Assert
        assert worker.running is False


class TestHandleRequestInner:
    """_handle_request_inner 方法測試"""

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_PING操作應該返回healthy(self, mock_signal, mock_redis_from_url):
        """測試: PING 操作應該返回 healthy 狀態"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()
        worker = TradingWorker()

        # Mock _get_api_client
        mock_api = Mock()
        worker._get_api_client = Mock(return_value=mock_api)

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.PING.value,
            simulation=True,
            params={},
        )

        # Act
        response = worker._handle_request_inner(request)

        # Assert
        assert response.success is True
        assert response.data["status"] == "healthy"
        assert response.data["simulation"] is True

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    @patch("trading_worker.get_valid_symbols_with_info")
    def test_GET_SYMBOLS操作應該返回符號列表(
        self, mock_get_symbols, mock_signal, mock_redis_from_url
    ):
        """測試: GET_SYMBOLS 操作應該返回符號列表"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()
        mock_get_symbols.return_value = [
            {"symbol": "MXFJ5", "code": "MXF202501"},
            {"symbol": "TXFK5", "code": "TXF202502"},
        ]

        worker = TradingWorker()
        worker._get_api_client = Mock(return_value=Mock())

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.GET_SYMBOLS.value,
            simulation=True,
            params={},
        )

        # Act
        response = worker._handle_request_inner(request)

        # Assert
        assert response.success is True
        assert response.data["count"] == 2
        assert len(response.data["symbols"]) == 2

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    @patch("trading_worker.get_contract_from_symbol")
    def test_GET_SYMBOL_INFO操作應該返回符號詳情(
        self, mock_get_contract, mock_signal, mock_redis_from_url
    ):
        """測試: GET_SYMBOL_INFO 操作應該返回符號詳細資訊"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        mock_contract = Mock()
        mock_contract.symbol = "MXFJ5"
        mock_contract.code = "MXF202501"
        mock_contract.name = "小型台指期貨"
        mock_contract.category = "MXF"
        mock_contract.delivery_month = "202501"
        mock_contract.underlying_kind = "I"
        mock_contract.limit_up = 22000
        mock_contract.limit_down = 20000
        mock_contract.reference = 21000
        mock_get_contract.return_value = mock_contract

        worker = TradingWorker()
        worker._get_api_client = Mock(return_value=Mock())

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.GET_SYMBOL_INFO.value,
            simulation=True,
            params={"symbol": "MXFJ5"},
        )

        # Act
        response = worker._handle_request_inner(request)

        # Assert
        assert response.success is True
        assert response.data["symbol"] == "MXFJ5"
        assert response.data["code"] == "MXF202501"
        assert response.data["name"] == "小型台指期貨"

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    @patch("trading_worker.get_valid_contract_codes")
    def test_GET_CONTRACT_CODES操作應該返回合約代碼(
        self, mock_get_codes, mock_signal, mock_redis_from_url
    ):
        """測試: GET_CONTRACT_CODES 操作應該返回合約代碼列表"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()
        mock_get_codes.return_value = ["MXFJ5", "MXFK5", "TXFJ5"]

        worker = TradingWorker()
        worker._get_api_client = Mock(return_value=Mock())

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.GET_CONTRACT_CODES.value,
            simulation=True,
            params={},
        )

        # Act
        response = worker._handle_request_inner(request)

        # Assert
        assert response.success is True
        assert response.data["count"] == 3

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_GET_POSITIONS操作應該返回持倉列表(self, mock_signal, mock_redis_from_url):
        """測試: GET_POSITIONS 操作應該返回持倉列表"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        # Mock position
        mock_position = Mock()
        mock_position.code = "MXFJ5"
        mock_position.direction = Mock(value="Buy")
        mock_position.quantity = 1
        mock_position.price = 21000.0
        mock_position.pnl = 500.0

        # Mock API
        mock_api = Mock()
        mock_api.futopt_account = Mock()
        mock_api.list_positions.return_value = [mock_position]

        # Mock Contracts.Futures
        mock_contract = Mock()
        mock_contract.code = "MXFJ5"
        mock_contract.symbol = "MXF202501"

        mock_mxf = [mock_contract]
        mock_futures = Mock()
        mock_futures.MXF = mock_mxf
        mock_api.Contracts.Futures = mock_futures

        worker = TradingWorker()
        worker._get_api_client = Mock(return_value=mock_api)

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.GET_POSITIONS.value,
            simulation=True,
            params={},
        )

        # Act
        response = worker._handle_request_inner(request)

        # Assert
        assert response.success is True
        assert len(response.data["positions"]) == 1
        assert response.data["positions"][0]["code"] == "MXFJ5"

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    @patch("trading_worker.get_contract_from_symbol")
    @patch("trading.get_snapshot")
    def test_GET_SNAPSHOT操作應該返回報價資料(
        self, mock_get_snapshot, mock_get_contract, mock_signal, mock_redis_from_url
    ):
        """測試: GET_SNAPSHOT 操作應該返回即時報價"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        mock_contract = Mock()
        mock_get_contract.return_value = mock_contract
        mock_get_snapshot.return_value = {
            "symbol": "MXFJ5",
            "close": 21500.0,
            "volume": 100,
        }

        worker = TradingWorker()
        worker._get_api_client = Mock(return_value=Mock())

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.GET_SNAPSHOT.value,
            simulation=True,
            params={"symbol": "MXFJ5"},
        )

        # Act
        response = worker._handle_request_inner(request)

        # Assert
        assert response.success is True
        assert response.data["close"] == 21500.0

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    @patch("trading_worker.get_contract_from_symbol")
    @patch("trading.get_snapshot")
    def test_GET_SNAPSHOT無資料時應該返回失敗(
        self, mock_get_snapshot, mock_get_contract, mock_signal, mock_redis_from_url
    ):
        """測試: GET_SNAPSHOT 無資料時應該返回失敗"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()
        mock_get_contract.return_value = Mock()
        mock_get_snapshot.return_value = None

        worker = TradingWorker()
        worker._get_api_client = Mock(return_value=Mock())

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.GET_SNAPSHOT.value,
            simulation=True,
            params={"symbol": "INVALID"},
        )

        # Act
        response = worker._handle_request_inner(request)

        # Assert
        assert response.success is False
        assert "No snapshot data" in response.error


class TestConnectionManagement:
    """連線管理測試"""

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_invalidate_connection應該清除API客戶端(
        self, mock_signal, mock_redis_from_url
    ):
        """測試: _invalidate_connection 應該清除 API 客戶端"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        worker = TradingWorker()
        mock_api = Mock()
        worker.api_clients[True] = mock_api

        # Act
        worker._invalidate_connection(simulation=True)

        # Assert
        assert worker.api_clients[True] is None

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_check_connection_health應該返回True當連線健康(
        self, mock_signal, mock_redis_from_url
    ):
        """測試: _check_connection_health 在連線健康時返回 True"""
        from trading_worker import TradingWorker
        import time

        # Arrange
        mock_redis_from_url.return_value = Mock()

        worker = TradingWorker()
        mock_api = Mock()
        mock_api.list_accounts.return_value = [Mock()]
        worker.api_clients[True] = mock_api
        worker._last_successful_request[True] = time.time()

        # Act
        result = worker._check_connection_health(simulation=True)

        # Assert
        assert result is True

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_check_connection_health應該返回False當無客戶端(
        self, mock_signal, mock_redis_from_url
    ):
        """測試: _check_connection_health 在無客戶端時返回 False"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        worker = TradingWorker()
        worker.api_clients[True] = None

        # Act
        result = worker._check_connection_health(simulation=True)

        # Assert
        assert result is False


class TestHandleRequest:
    """_handle_request 方法測試（包含重試邏輯）"""

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_handle_request成功時應該返回回應(self, mock_signal, mock_redis_from_url):
        """測試: _handle_request 成功時應該返回正確回應"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        worker = TradingWorker()

        # Mock _handle_request_inner
        expected_response = TradingResponse(
            request_id="test-123", success=True, data={"status": "ok"}
        )
        worker._handle_request_inner = Mock(return_value=expected_response)

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.PING.value,
            simulation=True,
            params={},
        )

        # Act
        response = worker._handle_request(request)

        # Assert
        assert response.success is True
        assert response.data["status"] == "ok"

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    @patch("trading_worker.time.sleep")
    def test_handle_request連線錯誤時應該重試(
        self, mock_sleep, mock_signal, mock_redis_from_url
    ):
        """測試: _handle_request 遇到可重試錯誤時應該重試"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        worker = TradingWorker()

        # 第一次返回可重試的錯誤（token expired），第二次成功
        error_response = TradingResponse(
            request_id="test-123",
            success=False,
            error="token is expired",  # 匹配可重試的錯誤模式
        )
        success_response = TradingResponse(
            request_id="test-123", success=True, data={"status": "ok"}
        )
        worker._handle_request_inner = Mock(
            side_effect=[error_response, success_response]
        )

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.PING.value,
            simulation=True,
            params={},
        )

        # Act
        response = worker._handle_request(request)

        # Assert
        assert response.success is True
        assert worker._handle_request_inner.call_count == 2
        mock_sleep.assert_called_once()  # 確認重試前有等待


class TestAccountOperations:
    """帳戶操作測試"""

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_GET_MARGIN操作應該返回保證金資訊(self, mock_signal, mock_redis_from_url):
        """測試: GET_MARGIN 操作應該返回保證金資訊"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        mock_margin = Mock()
        mock_margin.equity = 1000000
        mock_margin.available_margin = 800000
        mock_margin.excess_margin = 200000

        mock_api = Mock()
        mock_api.futopt_account = Mock()
        mock_api.margin.return_value = mock_margin

        worker = TradingWorker()
        worker._get_api_client = Mock(return_value=mock_api)

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.GET_MARGIN.value,
            simulation=True,
            params={},
        )

        # Act
        response = worker._handle_request_inner(request)

        # Assert
        assert response.success is True
        assert response.data["equity"] == 1000000

    @patch("trading_worker.redis.from_url")
    @patch("trading_worker.signal.signal")
    def test_LIST_TRADES操作應該返回成交紀錄(self, mock_signal, mock_redis_from_url):
        """測試: LIST_TRADES 操作應該返回成交紀錄"""
        from trading_worker import TradingWorker

        # Arrange
        mock_redis_from_url.return_value = Mock()

        mock_trade = Mock()
        mock_trade.code = "MXFJ5"
        mock_trade.price = 21000.0
        mock_trade.quantity = 1
        mock_trade.seqno = "seq-123"
        mock_trade.ordno = "ord-456"
        mock_trade.action = Mock(value="Buy")
        mock_trade.ts = 1234567890

        mock_api = Mock()
        mock_api.futopt_account = Mock()
        mock_api.list_trades.return_value = [mock_trade]

        worker = TradingWorker()
        worker._get_api_client = Mock(return_value=mock_api)

        request = TradingRequest(
            request_id="test-123",
            operation=TradingOperation.LIST_TRADES.value,
            simulation=True,
            params={},
        )

        # Act
        response = worker._handle_request_inner(request)

        # Assert
        assert response.success is True
        assert len(response.data["trades"]) == 1
        assert response.data["trades"][0]["code"] == "MXFJ5"

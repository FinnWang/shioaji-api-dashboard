"""
FastAPI API 端點單元測試

測試涵蓋：
1. 認證機制 (verify_auth_key)
2. OrderRequest 資料驗證
3. 查詢端點 (symbols, futures, contracts, snapshot)
4. 需認證端點 (positions, orders, trades, margin)
5. 下單端點 (POST /order)
6. 健康檢查端點
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock, PropertyMock
from fastapi.testclient import TestClient

from config import settings
from trading_queue import TradingResponse


def get_test_client_with_db_override(mock_db):
    """建立帶有資料庫依賴覆蓋的測試客戶端"""
    from main import app, get_db
    from database import get_db as db_get_db

    def override_get_db():
        return mock_db

    app.dependency_overrides[get_db] = override_get_db
    # 同時覆蓋從 database 模組導入的 get_db
    app.dependency_overrides[db_get_db] = override_get_db

    return TestClient(app)


def cleanup_overrides():
    """清理依賴覆蓋"""
    from main import app
    app.dependency_overrides.clear()


class TestOrderRequestValidation:
    """OrderRequest Pydantic 模型驗證測試"""

    def test_有效的市價單應該通過驗證(self):
        """測試: 有效的市價單應該通過驗證"""
        from main import OrderRequest

        # Act
        order = OrderRequest(
            action="long_entry",
            quantity=1,
            symbol="MXFJ5",
            price_type="MKT",
        )

        # Assert
        assert order.action == "long_entry"
        assert order.quantity == 1
        assert order.symbol == "MXFJ5"
        assert order.price_type == "MKT"
        assert order.price is None

    def test_有效的限價單應該通過驗證(self):
        """測試: 有效的限價單（含價格）應該通過驗證"""
        from main import OrderRequest

        # Act
        order = OrderRequest(
            action="short_entry",
            quantity=2,
            symbol="TXFK5",
            price_type="LMT",
            price=21000.0,
        )

        # Assert
        assert order.price_type == "LMT"
        assert order.price == 21000.0

    def test_限價單缺少價格應該拋出驗證錯誤(self):
        """測試: 限價單缺少 price 應該拋出 ValidationError"""
        from main import OrderRequest
        from pydantic import ValidationError

        # Act & Assert
        with pytest.raises(ValidationError, match="price must be provided"):
            OrderRequest(
                action="long_entry",
                quantity=1,
                symbol="MXFJ5",
                price_type="LMT",
                price=None,
            )

    def test_限價單價格為零應該拋出驗證錯誤(self):
        """測試: 限價單 price=0 應該拋出 ValidationError"""
        from main import OrderRequest
        from pydantic import ValidationError

        # Act & Assert
        with pytest.raises(ValidationError, match="price must be provided and > 0"):
            OrderRequest(
                action="long_entry",
                quantity=1,
                symbol="MXFJ5",
                price_type="LMT",
                price=0,
            )

    def test_無效的價格類型應該拋出驗證錯誤(self):
        """測試: 無效的 price_type 應該拋出 ValidationError"""
        from main import OrderRequest
        from pydantic import ValidationError

        # Act & Assert
        with pytest.raises(ValidationError, match="price_type must be"):
            OrderRequest(
                action="long_entry",
                quantity=1,
                symbol="MXFJ5",
                price_type="INVALID",
            )

    def test_數量為零應該拋出驗證錯誤(self):
        """測試: quantity=0 應該拋出 ValidationError"""
        from main import OrderRequest
        from pydantic import ValidationError

        # Act & Assert
        with pytest.raises(ValidationError):
            OrderRequest(
                action="long_entry",
                quantity=0,
                symbol="MXFJ5",
            )

    def test_無效的action應該拋出驗證錯誤(self):
        """測試: 無效的 action 應該拋出 ValidationError"""
        from main import OrderRequest
        from pydantic import ValidationError

        # Act & Assert
        with pytest.raises(ValidationError):
            OrderRequest(
                action="invalid_action",
                quantity=1,
                symbol="MXFJ5",
            )


class TestVerifyAuthKey:
    """認證機制測試"""

    @patch("main.get_queue_client")
    def test_正確的認證金鑰應該通過(self, mock_get_client):
        """測試: 正確的 X-Auth-Key 應該通過認證"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_positions.return_value = TradingResponse(
            request_id="test", success=True, data={"positions": []}
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        with patch.object(settings, "auth_key", "test-key"):
            response = client.get("/positions", headers={"X-Auth-Key": "test-key"})

        # Assert
        assert response.status_code == 200

    def test_缺少認證金鑰應該返回422(self):
        """測試: 缺少 X-Auth-Key 應該返回 422"""
        from main import app

        client = TestClient(app)

        # Act
        response = client.get("/positions")

        # Assert
        assert response.status_code == 422

    def test_錯誤的認證金鑰應該返回401(self):
        """測試: 錯誤的 X-Auth-Key 應該返回 401"""
        from main import app

        client = TestClient(app)

        # Act
        with patch.object(settings, "auth_key", "correct-key"):
            response = client.get("/positions", headers={"X-Auth-Key": "wrong-key"})

        # Assert
        assert response.status_code == 401
        assert "Invalid authentication key" in response.json()["detail"]


class TestHealthEndpoint:
    """健康檢查端點測試"""

    @patch("main.get_queue_client")
    def test_health_所有服務健康時應該返回healthy(self, mock_get_client):
        """測試: 所有服務健康時 /health 應該返回 healthy"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.check_worker_health.return_value = True
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["api"] == "healthy"
        assert data["trading_worker"] == "healthy"
        assert data["redis"] == "connected"

    @patch("main.get_queue_client")
    def test_health_Worker不健康時應該返回unhealthy(self, mock_get_client):
        """測試: Worker 不健康時應該返回 unhealthy"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.check_worker_health.return_value = False
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["api"] == "healthy"
        assert data["trading_worker"] == "unhealthy"

    @patch("main.get_queue_client")
    def test_health_Redis連線失敗時應該返回disconnected(self, mock_get_client):
        """測試: Redis 連線失敗時應該返回 disconnected"""
        from main import app

        # Arrange
        mock_get_client.side_effect = ConnectionError("Redis connection failed")

        client = TestClient(app)

        # Act
        response = client.get("/health")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["api"] == "healthy"
        assert data["redis"] == "disconnected"


class TestSymbolsEndpoints:
    """符號查詢端點測試"""

    @patch("main.get_queue_client")
    def test_get_symbols_成功時應該返回符號列表(self, mock_get_client):
        """測試: GET /symbols 成功時應該返回符號列表"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_symbols.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={"symbols": ["MXFJ5", "TXFK5"]},
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/symbols")

        # Assert
        assert response.status_code == 200
        assert response.json() == {"symbols": ["MXFJ5", "TXFK5"]}

    @patch("main.get_queue_client")
    def test_get_symbols_服務失敗時應該返回503(self, mock_get_client):
        """測試: GET /symbols 服務失敗時應該返回 503"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_symbols.return_value = TradingResponse(
            request_id="test",
            success=False,
            error="Service unavailable",
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/symbols")

        # Assert
        assert response.status_code == 503

    @patch("main.get_queue_client")
    def test_get_symbols_超時時應該返回503(self, mock_get_client):
        """測試: GET /symbols 超時時應該返回 503"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_symbols.side_effect = TimeoutError("Request timed out")
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/symbols")

        # Assert
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"]

    @patch("main.get_queue_client")
    def test_get_symbol_details_成功時應該返回詳情(self, mock_get_client):
        """測試: GET /symbols/{symbol} 成功時應該返回符號詳情"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_symbol_info.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "symbol": "MXFJ5",
                "code": "MXF202501",
                "name": "小型台指期貨",
            },
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/symbols/MXFJ5")

        # Assert
        assert response.status_code == 200
        assert response.json()["symbol"] == "MXFJ5"

    @patch("main.get_queue_client")
    def test_get_symbol_details_不存在時應該返回404(self, mock_get_client):
        """測試: GET /symbols/{symbol} 符號不存在時應該返回 404"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_symbol_info.return_value = TradingResponse(
            request_id="test",
            success=False,
            error="Symbol not found: INVALID",
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/symbols/INVALID")

        # Assert
        assert response.status_code == 404


class TestSnapshotEndpoint:
    """即時報價端點測試"""

    @patch("main.get_queue_client")
    def test_get_snapshot_成功時應該返回報價資料(self, mock_get_client):
        """測試: GET /symbols/{symbol}/snapshot 成功時應該返回報價"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_snapshot.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "symbol": "MXFJ5",
                "close": 21500.0,
                "open": 21400.0,
                "high": 21600.0,
                "low": 21300.0,
                "volume": 100,
            },
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/symbols/MXFJ5/snapshot")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "MXFJ5"
        assert data["close"] == 21500.0

    @patch("main.get_queue_client")
    def test_get_snapshot_符號不存在時應該返回404(self, mock_get_client):
        """測試: GET /symbols/{symbol}/snapshot 符號不存在時返回 404"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_snapshot.return_value = TradingResponse(
            request_id="test",
            success=False,
            error="Symbol not found",
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/symbols/INVALID/snapshot")

        # Assert
        assert response.status_code == 404


class TestFuturesEndpoints:
    """期貨端點測試"""

    @patch("main.get_queue_client")
    def test_list_futures_products_成功時應該返回產品列表(self, mock_get_client):
        """測試: GET /futures 成功時應該返回期貨產品列表"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_futures_overview.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "products": [
                    {
                        "product": "MXF",
                        "contracts": [{"name": "小型台指期貨", "code": "MXFJ5"}],
                    },
                    {
                        "product": "TXF",
                        "contracts": [{"name": "台指期貨", "code": "TXFK5"}],
                    },
                ]
            },
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/futures")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 2
        assert len(data["products"]) == 2

    @patch("main.get_queue_client")
    def test_list_futures_contracts_成功時應該返回合約列表(self, mock_get_client):
        """測試: GET /futures/{code} 成功時應該返回合約列表"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_product_contracts.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "contracts": [
                    {"code": "MXFJ5", "name": "小型台指期貨"},
                    {"code": "MXFK5", "name": "小型台指期貨"},
                ]
            },
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/futures/MXF")

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["product_code"] == "MXF"
        assert data["count"] == 2

    @patch("main.get_queue_client")
    def test_list_futures_contracts_產品不存在時應該返回404(self, mock_get_client):
        """測試: GET /futures/{code} 產品不存在時返回 404"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_product_contracts.return_value = TradingResponse(
            request_id="test",
            success=False,
            error="Product not found",
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        response = client.get("/futures/INVALID")

        # Assert
        assert response.status_code == 404


class TestPositionsEndpoint:
    """持倉端點測試"""

    @patch("main.get_queue_client")
    def test_get_positions_成功時應該返回持倉(self, mock_get_client):
        """測試: GET /positions 成功時應該返回持倉列表"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_positions.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "positions": [
                    {"symbol": "MXFJ5", "direction": "Buy", "quantity": 1},
                ]
            },
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        with patch.object(settings, "auth_key", "test-key"):
            response = client.get("/positions", headers={"X-Auth-Key": "test-key"})

        # Assert
        assert response.status_code == 200
        assert "positions" in response.json()

    @patch("main.get_queue_client")
    def test_get_positions_超時時應該返回503(self, mock_get_client):
        """測試: GET /positions 超時時返回 503"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_positions.side_effect = TimeoutError("Connection timeout")
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        with patch.object(settings, "auth_key", "test-key"):
            response = client.get("/positions", headers={"X-Auth-Key": "test-key"})

        # Assert
        assert response.status_code == 503
        assert "unavailable" in response.json()["detail"]


class TestOrderEndpoint:
    """下單端點測試"""

    def teardown_method(self, method):
        """每個測試後清理依賴覆蓋"""
        cleanup_overrides()

    @patch("main.get_queue_client")
    def test_create_order_long_entry_成功(self, mock_get_client):
        """測試: POST /order long_entry 成功時應該返回訂單資訊"""
        # Arrange
        mock_client = Mock()
        mock_client.place_entry_order.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "order_id": "order-123",
                "seqno": "seq-456",
                "ordno": "ord-789",
                "symbol": "MXFJ5",
            },
        )
        mock_get_client.return_value = mock_client

        # Mock database
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        client = get_test_client_with_db_override(mock_db)

        # Act
        response = client.post(
            "/order",
            json={
                "action": "long_entry",
                "quantity": 1,
                "symbol": "MXFJ5",
                "price_type": "MKT",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert "order_id" in data

    @patch("main.get_queue_client")
    def test_create_order_limit_order_成功(self, mock_get_client):
        """測試: POST /order 限價單成功時應該返回訂單資訊"""
        # Arrange
        mock_client = Mock()
        mock_client.place_entry_order.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "order_id": "order-123",
                "seqno": "seq-456",
                "symbol": "MXFJ5",
            },
        )
        mock_get_client.return_value = mock_client

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        client = get_test_client_with_db_override(mock_db)

        # Act
        response = client.post(
            "/order",
            json={
                "action": "long_entry",
                "quantity": 1,
                "symbol": "MXFJ5",
                "price_type": "LMT",
                "price": 21000.0,
            },
        )

        # Assert
        assert response.status_code == 200
        # 驗證 place_entry_order 被正確調用
        mock_client.place_entry_order.assert_called_once()
        call_kwargs = mock_client.place_entry_order.call_args[1]
        assert call_kwargs["price_type"] == "LMT"
        assert call_kwargs["price"] == 21000.0

    @patch("main.get_queue_client")
    def test_create_order_short_entry_成功(self, mock_get_client):
        """測試: POST /order short_entry 應該調用 Sell action"""
        # Arrange
        mock_client = Mock()
        mock_client.place_entry_order.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={"order_id": "order-123", "seqno": "seq-456"},
        )
        mock_get_client.return_value = mock_client

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        client = get_test_client_with_db_override(mock_db)

        # Act
        response = client.post(
            "/order",
            json={
                "action": "short_entry",
                "quantity": 1,
                "symbol": "MXFJ5",
            },
        )

        # Assert
        assert response.status_code == 200
        mock_client.place_entry_order.assert_called_once()
        call_kwargs = mock_client.place_entry_order.call_args[1]
        assert call_kwargs["action"] == "Sell"

    @patch("main.get_queue_client")
    def test_create_order_long_exit_成功(self, mock_get_client):
        """測試: POST /order long_exit 應該調用 place_exit_order"""
        # Arrange
        mock_client = Mock()
        mock_client.place_exit_order.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={"order_id": "order-123", "seqno": "seq-456", "quantity": 1},
        )
        mock_get_client.return_value = mock_client

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        client = get_test_client_with_db_override(mock_db)

        # Act
        response = client.post(
            "/order",
            json={
                "action": "long_exit",
                "quantity": 1,
                "symbol": "MXFJ5",
            },
        )

        # Assert
        assert response.status_code == 200
        mock_client.place_exit_order.assert_called_once()
        call_kwargs = mock_client.place_exit_order.call_args[1]
        assert call_kwargs["position_direction"] == "Buy"

    @patch("main.get_queue_client")
    def test_create_order_服務失敗時應該返回400(self, mock_get_client):
        """測試: POST /order 服務返回失敗時應該返回 400"""
        # Arrange
        mock_client = Mock()
        mock_client.place_entry_order.return_value = TradingResponse(
            request_id="test",
            success=False,
            error="Invalid symbol",
        )
        mock_get_client.return_value = mock_client

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()

        client = get_test_client_with_db_override(mock_db)

        # Act
        response = client.post(
            "/order",
            json={
                "action": "long_entry",
                "quantity": 1,
                "symbol": "INVALID",
            },
        )

        # Assert
        assert response.status_code == 400
        assert "Invalid symbol" in response.json()["detail"]

    @patch("main.get_queue_client")
    def test_create_order_超時時應該返回503(self, mock_get_client):
        """測試: POST /order 超時時應該返回 503"""
        # Arrange
        mock_client = Mock()
        mock_client.place_entry_order.side_effect = TimeoutError("Timeout")
        mock_get_client.return_value = mock_client

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()

        client = get_test_client_with_db_override(mock_db)

        # Act
        response = client.post(
            "/order",
            json={
                "action": "long_entry",
                "quantity": 1,
                "symbol": "MXFJ5",
            },
        )

        # Assert
        assert response.status_code == 503

    @patch("main.get_queue_client")
    def test_create_order_no_position_應該返回no_action(self, mock_get_client):
        """測試: POST /order 無持倉時應該返回 no_action"""
        # Arrange
        mock_client = Mock()
        mock_client.place_exit_order.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "order_id": None,
                "message": "No position to exit",
            },
        )
        mock_get_client.return_value = mock_client

        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_db.commit = MagicMock()

        client = get_test_client_with_db_override(mock_db)

        # Act
        response = client.post(
            "/order",
            json={
                "action": "long_exit",
                "quantity": 1,
                "symbol": "MXFJ5",
            },
        )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "no_action"


class TestOrdersEndpoint:
    """訂單查詢端點測試"""

    def teardown_method(self, method):
        """每個測試後清理依賴覆蓋"""
        cleanup_overrides()

    def test_get_orders_應該返回訂單列表(self):
        """測試: GET /orders 應該返回訂單列表"""
        # Arrange
        mock_order = MagicMock()
        mock_order.id = 1
        mock_order.symbol = "MXFJ5"
        mock_order.code = None
        mock_order.action = "long_entry"
        mock_order.quantity = 1
        mock_order.status = "filled"
        mock_order.order_result = None
        mock_order.error_message = None
        mock_order.created_at = datetime.now(timezone.utc)
        mock_order.order_id = "order-123"
        mock_order.fill_status = "Filled"
        mock_order.fill_quantity = 1
        mock_order.fill_price = 21000.0
        mock_order.updated_at = datetime.now(timezone.utc)

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            mock_order
        ]
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        # Act
        with patch.object(settings, "auth_key", "test-key"):
            response = client.get("/orders", headers={"X-Auth-Key": "test-key"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["symbol"] == "MXFJ5"


class TestTradesEndpoint:
    """成交紀錄端點測試"""

    @patch("main.get_queue_client")
    def test_get_trades_成功時應該返回成交列表(self, mock_get_client):
        """測試: GET /trades 成功時應該返回成交紀錄"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.list_trades.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "trades": [
                    {"symbol": "MXFJ5", "price": 21000.0, "quantity": 1},
                ]
            },
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        with patch.object(settings, "auth_key", "test-key"):
            response = client.get("/trades", headers={"X-Auth-Key": "test-key"})

        # Assert
        assert response.status_code == 200
        assert "trades" in response.json()


class TestMarginEndpoint:
    """保證金端點測試"""

    @patch("main.get_queue_client")
    def test_get_margin_成功時應該返回保證金資訊(self, mock_get_client):
        """測試: GET /margin 成功時應該返回保證金資訊"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_margin.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "equity": 1000000,
                "available_margin": 800000,
            },
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        with patch.object(settings, "auth_key", "test-key"):
            response = client.get("/margin", headers={"X-Auth-Key": "test-key"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["equity"] == 1000000


class TestUsageEndpoint:
    """API 使用量端點測試"""

    @patch("main.get_queue_client")
    def test_get_usage_成功時應該返回使用量資訊(self, mock_get_client):
        """測試: GET /usage 成功時應該返回 API 使用量"""
        from main import app

        # Arrange
        mock_client = Mock()
        mock_client.get_usage.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "connections": 1,
                "bytes": 1024,
            },
        )
        mock_get_client.return_value = mock_client

        client = TestClient(app)

        # Act
        with patch.object(settings, "auth_key", "test-key"):
            response = client.get("/usage", headers={"X-Auth-Key": "test-key"})

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["connections"] == 1


class TestRecheckOrderEndpoint:
    """重新檢查訂單狀態端點測試"""

    def teardown_method(self, method):
        """每個測試後清理依賴覆蓋"""
        cleanup_overrides()

    @patch("main.get_queue_client")
    def test_recheck_order_成功時應該更新狀態(self, mock_get_client):
        """測試: POST /orders/{id}/recheck 成功時應該更新訂單狀態"""
        # Arrange
        mock_order = MagicMock()
        mock_order.id = 1
        mock_order.order_id = "order-123"
        mock_order.seqno = "seq-456"
        mock_order.status = "submitted"
        mock_order.fill_status = "Submitted"

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_order
        mock_db.commit = MagicMock()
        mock_db.refresh = MagicMock()

        mock_client = Mock()
        mock_client.check_order_status.return_value = TradingResponse(
            request_id="test",
            success=True,
            data={
                "status": "Filled",
                "deal_quantity": 1,
                "fill_avg_price": 21000.0,
                "deals": [],
            },
        )
        mock_get_client.return_value = mock_client

        client = get_test_client_with_db_override(mock_db)

        # Act
        with patch.object(settings, "auth_key", "test-key"):
            response = client.post(
                "/orders/1/recheck", headers={"X-Auth-Key": "test-key"}
            )

        # Assert
        assert response.status_code == 200
        data = response.json()
        assert data["current_fill_status"] == "Filled"

    def test_recheck_order_訂單不存在時應該返回404(self):
        """測試: POST /orders/{id}/recheck 訂單不存在時返回 404"""
        # Arrange
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        client = get_test_client_with_db_override(mock_db)

        # Act
        with patch.object(settings, "auth_key", "test-key"):
            response = client.post(
                "/orders/999/recheck", headers={"X-Auth-Key": "test-key"}
            )

        # Assert
        assert response.status_code == 404

    def test_recheck_order_無seqno時應該返回400(self):
        """測試: POST /orders/{id}/recheck 訂單無 seqno 時返回 400"""
        # Arrange
        mock_order = MagicMock()
        mock_order.id = 1
        mock_order.order_id = None
        mock_order.seqno = None

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_order

        client = get_test_client_with_db_override(mock_db)

        # Act
        with patch.object(settings, "auth_key", "test-key"):
            response = client.post(
                "/orders/1/recheck", headers={"X-Auth-Key": "test-key"}
            )

        # Assert
        assert response.status_code == 400
        assert "seqno" in response.json()["detail"]

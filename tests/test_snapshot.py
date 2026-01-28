"""
Tests for snapshot (即時報價) functionality.

TDD: 先寫測試，再實作功能
"""
import pytest
from unittest.mock import Mock, MagicMock, patch


class TestGetSnapshot:
    """Test get_snapshot function in trading.py"""
    
    def test_get_snapshot_returns_price_data(self):
        """Snapshot 應該回傳即時價格資料"""
        # Arrange
        mock_api = Mock()
        mock_contract = Mock()
        mock_contract.symbol = "MXF202501"
        
        # Mock snapshot response
        mock_snapshot = Mock()
        mock_snapshot.close = 23500.0
        mock_snapshot.open = 23400.0
        mock_snapshot.high = 23600.0
        mock_snapshot.low = 23300.0
        mock_snapshot.volume = 12345
        mock_snapshot.total_volume = 98765
        mock_snapshot.buy_price = 23499.0
        mock_snapshot.sell_price = 23501.0
        mock_snapshot.change_price = 100.0
        mock_snapshot.change_rate = 0.43
        mock_snapshot.ts = 1705395600000000000  # nanoseconds
        
        mock_api.snapshots.return_value = [mock_snapshot]
        
        # Act
        from trading import get_snapshot
        result = get_snapshot(mock_api, mock_contract)
        
        # Assert
        assert result is not None
        assert result["close"] == 23500.0
        assert result["open"] == 23400.0
        assert result["high"] == 23600.0
        assert result["low"] == 23300.0
        assert result["volume"] == 12345
        assert result["buy_price"] == 23499.0
        assert result["sell_price"] == 23501.0
        assert result["change_price"] == 100.0
        assert result["change_rate"] == 0.43
        
    def test_get_snapshot_handles_empty_response(self):
        """Snapshot 回傳空值時應該回傳 None"""
        mock_api = Mock()
        mock_contract = Mock()
        mock_api.snapshots.return_value = []
        
        from trading import get_snapshot
        result = get_snapshot(mock_api, mock_contract)
        
        assert result is None
        
    def test_get_snapshot_handles_exception(self):
        """Snapshot 發生錯誤時應該回傳 None 並記錄錯誤"""
        mock_api = Mock()
        mock_contract = Mock()
        mock_api.snapshots.side_effect = Exception("API Error")
        
        from trading import get_snapshot
        result = get_snapshot(mock_api, mock_contract)
        
        assert result is None


class TestSnapshotAPI:
    """Test snapshot API endpoint"""
    
    @pytest.fixture
    def mock_queue_client(self):
        with patch('main.get_queue_client') as mock:
            yield mock
    
    def test_snapshot_endpoint_returns_price(self, mock_queue_client):
        """GET /symbols/{symbol}/snapshot 應該回傳即時價格"""
        from fastapi.testclient import TestClient
        from main import app
        
        # Mock response
        mock_response = Mock()
        mock_response.success = True
        mock_response.data = {
            "symbol": "MXF202501",
            "close": 23500.0,
            "open": 23400.0,
            "high": 23600.0,
            "low": 23300.0,
            "buy_price": 23499.0,
            "sell_price": 23501.0,
            "change_price": 100.0,
            "change_rate": 0.43,
            "volume": 12345,
            "ts": 1705395600000,
        }
        mock_queue_client.return_value.get_snapshot.return_value = mock_response
        
        client = TestClient(app)
        response = client.get("/symbols/MXF202501/snapshot?simulation=true")
        
        assert response.status_code == 200
        data = response.json()
        assert data["close"] == 23500.0
        assert data["buy_price"] == 23499.0
        assert data["sell_price"] == 23501.0


class TestTradingQueueSnapshot:
    """Test TradingQueueClient.get_snapshot method"""
    
    def test_queue_client_has_get_snapshot_method(self):
        """TradingQueueClient 應該有 get_snapshot 方法"""
        from trading_queue import TradingQueueClient, TradingOperation
        
        # Verify operation exists
        assert hasattr(TradingOperation, 'GET_SNAPSHOT')
        
        # Verify method exists (will fail until implemented)
        assert hasattr(TradingQueueClient, 'get_snapshot')

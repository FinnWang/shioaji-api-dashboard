"""
報價歷史 API 端點測試

測試涵蓋：
1. GET /quotes/history - 查詢報價歷史
2. GET /quotes/history/count - 取得報價歷史筆數
3. GET /quotes/history/export - 匯出報價歷史 (CSV/JSON)
4. GET /quotes/symbols - 取得有報價歷史的商品列表
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, MagicMock, patch
from fastapi.testclient import TestClient
from decimal import Decimal


def get_test_client_with_db_override(mock_db):
    """建立帶有資料庫依賴覆蓋的測試客戶端"""
    from main import app
    from database import get_db

    def override_get_db():
        return mock_db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def cleanup_overrides():
    """清理依賴覆蓋"""
    from main import app
    app.dependency_overrides.clear()


def create_mock_quote_history(
    id: int,
    symbol: str = "MXFR1",
    code: str = "MXFA6",
    quote_type: str = "tick",
    close_price: float = 21500.0,
    quote_time: datetime = None,
):
    """建立模擬的 QuoteHistory 物件"""
    mock_quote = MagicMock()
    mock_quote.id = id
    mock_quote.symbol = symbol
    mock_quote.code = code
    mock_quote.quote_type = quote_type
    mock_quote.close_price = Decimal(str(close_price)) if close_price else None
    mock_quote.open_price = Decimal("21400.0")
    mock_quote.high_price = Decimal("21600.0")
    mock_quote.low_price = Decimal("21350.0")
    mock_quote.change_price = Decimal("100.0")
    mock_quote.change_rate = Decimal("0.47")
    mock_quote.volume = 150
    mock_quote.total_volume = 52000
    mock_quote.buy_price = Decimal("21499.0")
    mock_quote.sell_price = Decimal("21501.0")
    mock_quote.buy_volume = 50
    mock_quote.sell_volume = 60
    mock_quote.quote_time = quote_time or datetime.now(timezone.utc)
    mock_quote.created_at = datetime.now(timezone.utc)

    # 設定 to_dict 方法
    mock_quote.to_dict.return_value = {
        "id": id,
        "symbol": symbol,
        "code": code,
        "quote_type": quote_type,
        "close_price": float(close_price) if close_price else None,
        "open_price": 21400.0,
        "high_price": 21600.0,
        "low_price": 21350.0,
        "change_price": 100.0,
        "change_rate": 0.47,
        "volume": 150,
        "total_volume": 52000,
        "buy_price": 21499.0,
        "sell_price": 21501.0,
        "buy_volume": 50,
        "sell_volume": 60,
        "quote_time": mock_quote.quote_time.isoformat(),
        "created_at": mock_quote.created_at.isoformat(),
    }

    return mock_quote


class TestGetQuoteHistory:
    """GET /quotes/history 測試"""

    def test_查詢報價歷史應該返回列表(self):
        """測試: 查詢報價歷史應該返回報價列表"""
        # Arrange
        mock_db = MagicMock()
        mock_quotes = [
            create_mock_quote_history(id=1, close_price=21500.0),
            create_mock_quote_history(id=2, close_price=21501.0),
        ]

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_quotes
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get("/quotes/history")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["id"] == 1
            assert data[1]["id"] == 2
        finally:
            cleanup_overrides()

    def test_依symbol篩選應該正確過濾(self):
        """測試: 依 symbol 篩選應該正確過濾結果"""
        # Arrange
        mock_db = MagicMock()
        mock_quotes = [
            create_mock_quote_history(id=1, symbol="MXFR1"),
        ]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_quotes
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get("/quotes/history?symbol=MXFR1")

            # Assert
            assert response.status_code == 200
            mock_query.filter.assert_called()
        finally:
            cleanup_overrides()

    def test_依quote_type篩選應該正確過濾(self):
        """測試: 依 quote_type 篩選應該正確過濾結果"""
        # Arrange
        mock_db = MagicMock()
        mock_quotes = [
            create_mock_quote_history(id=1, quote_type="tick"),
        ]

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_quotes
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get("/quotes/history?quote_type=tick")

            # Assert
            assert response.status_code == 200
        finally:
            cleanup_overrides()

    def test_分頁參數應該正確套用(self):
        """測試: limit 和 offset 應該正確套用"""
        # Arrange
        mock_db = MagicMock()

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.offset.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get("/quotes/history?limit=50&offset=100")

            # Assert
            assert response.status_code == 200
            mock_query.offset.assert_called_with(100)
            mock_query.limit.assert_called_with(50)
        finally:
            cleanup_overrides()


class TestGetQuoteHistoryCount:
    """GET /quotes/history/count 測試"""

    def test_取得報價歷史筆數(self):
        """測試: 應該返回報價歷史總筆數"""
        # Arrange
        mock_db = MagicMock()

        mock_query = MagicMock()
        mock_query.count.return_value = 12345
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get("/quotes/history/count")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 12345
        finally:
            cleanup_overrides()

    def test_帶篩選條件取得筆數(self):
        """測試: 帶篩選條件時應該返回符合條件的筆數"""
        # Arrange
        mock_db = MagicMock()

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 500
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get("/quotes/history/count?symbol=MXFR1&quote_type=tick")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 500
        finally:
            cleanup_overrides()


class TestExportQuoteHistory:
    """GET /quotes/history/export 測試"""

    def test_匯出JSON格式(self):
        """測試: format=json 應該返回 JSON 陣列"""
        # Arrange
        mock_db = MagicMock()
        mock_quotes = [
            create_mock_quote_history(id=1),
            create_mock_quote_history(id=2),
        ]

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_quotes
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get("/quotes/history/export?format=json")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["id"] == 1
        finally:
            cleanup_overrides()

    def test_匯出CSV格式(self):
        """測試: format=csv 應該返回 CSV 檔案"""
        # Arrange
        mock_db = MagicMock()
        mock_quotes = [
            create_mock_quote_history(id=1, symbol="MXFR1"),
        ]

        mock_query = MagicMock()
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = mock_quotes
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get("/quotes/history/export?format=csv")

            # Assert
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/csv; charset=utf-8"
            assert "attachment" in response.headers["content-disposition"]

            # 驗證 CSV 內容
            content = response.text
            assert "id,symbol,code,quote_type" in content
            assert "MXFR1" in content
        finally:
            cleanup_overrides()

    def test_匯出帶篩選條件(self):
        """測試: 匯出時應該套用篩選條件"""
        # Arrange
        mock_db = MagicMock()

        mock_query = MagicMock()
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get(
                "/quotes/history/export?symbol=MXFR1&quote_type=tick&format=json"
            )

            # Assert
            assert response.status_code == 200
            mock_query.filter.assert_called()
        finally:
            cleanup_overrides()


class TestGetQuoteSymbols:
    """GET /quotes/symbols 測試"""

    def test_取得有報價歷史的商品列表(self):
        """測試: 應該返回有報價歷史的商品代碼列表"""
        # Arrange
        mock_db = MagicMock()

        # 模擬 distinct 查詢結果
        mock_query = MagicMock()
        mock_query.all.return_value = [("MXFR1",), ("TXFR1",), ("TMFR1",)]
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get("/quotes/symbols")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 3
            assert "MXFR1" in data["symbols"]
            assert "TXFR1" in data["symbols"]
            assert "TMFR1" in data["symbols"]
        finally:
            cleanup_overrides()

    def test_無報價歷史時返回空列表(self):
        """測試: 無報價歷史時應該返回空列表"""
        # Arrange
        mock_db = MagicMock()

        mock_query = MagicMock()
        mock_query.all.return_value = []
        mock_db.query.return_value = mock_query

        client = get_test_client_with_db_override(mock_db)

        try:
            # Act
            response = client.get("/quotes/symbols")

            # Assert
            assert response.status_code == 200
            data = response.json()
            assert data["count"] == 0
            assert data["symbols"] == []
        finally:
            cleanup_overrides()


class TestQuoteHistoryResponseModel:
    """QuoteHistoryResponse 模型測試"""

    def test_模型應該正確處理Decimal欄位(self):
        """測試: 模型應該正確處理 Decimal 類型的價格欄位"""
        from main import QuoteHistoryResponse

        # Arrange
        mock_quote = MagicMock()
        mock_quote.id = 1
        mock_quote.symbol = "MXFR1"
        mock_quote.code = "MXFA6"
        mock_quote.quote_type = "tick"
        mock_quote.close_price = Decimal("21500.00")
        mock_quote.open_price = Decimal("21400.00")
        mock_quote.high_price = Decimal("21600.00")
        mock_quote.low_price = Decimal("21350.00")
        mock_quote.change_price = Decimal("100.00")
        mock_quote.change_rate = Decimal("0.4700")
        mock_quote.volume = 150
        mock_quote.total_volume = 52000
        mock_quote.buy_price = Decimal("21499.00")
        mock_quote.sell_price = Decimal("21501.00")
        mock_quote.buy_volume = 50
        mock_quote.sell_volume = 60
        mock_quote.quote_time = datetime.now(timezone.utc)
        mock_quote.created_at = datetime.now(timezone.utc)

        # Act
        response = QuoteHistoryResponse.model_validate(mock_quote)

        # Assert
        assert response.close_price == 21500.00
        assert response.change_rate == 0.47

    def test_模型應該允許None欄位(self):
        """測試: 模型應該允許可選欄位為 None"""
        from main import QuoteHistoryResponse

        # Arrange
        mock_quote = MagicMock()
        mock_quote.id = 1
        mock_quote.symbol = "MXFR1"
        mock_quote.code = "MXFA6"
        mock_quote.quote_type = "bidask"
        mock_quote.close_price = None  # BidAsk 沒有成交價
        mock_quote.open_price = None
        mock_quote.high_price = None
        mock_quote.low_price = None
        mock_quote.change_price = None
        mock_quote.change_rate = None
        mock_quote.volume = None
        mock_quote.total_volume = None
        mock_quote.buy_price = Decimal("21499.00")
        mock_quote.sell_price = Decimal("21501.00")
        mock_quote.buy_volume = 50
        mock_quote.sell_volume = 60
        mock_quote.quote_time = datetime.now(timezone.utc)
        mock_quote.created_at = None

        # Act
        response = QuoteHistoryResponse.model_validate(mock_quote)

        # Assert
        assert response.close_price is None
        assert response.buy_price == 21499.00
        assert response.created_at is None

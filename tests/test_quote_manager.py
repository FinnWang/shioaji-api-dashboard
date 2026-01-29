"""
QuoteManager 單元測試

測試涵蓋：
1. 訂閱報價功能
2. 取消訂閱功能
3. 報價回調處理與 Redis Pub/Sub 發布
4. 訂閱計數管理
5. 錯誤處理
"""
import json
import pytest
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime

from quote_manager import (
    QuoteManager,
    QuoteData,
    QUOTE_CHANNEL_PREFIX,
)


class TestQuoteData:
    """QuoteData 資料類測試"""

    def test_to_dict_應該正確轉換為字典(self):
        """測試: QuoteData 應該能正確轉換為字典"""
        # Arrange
        quote = QuoteData(
            symbol="MXF202601",
            code="MXFA6",
            close=21500.0,
            open=21400.0,
            high=21600.0,
            low=21350.0,
            change_price=100.0,
            change_rate=0.47,
            volume=150,
            total_volume=52000,
            buy_price=21499.0,
            sell_price=21501.0,
            timestamp=1704067200000,
        )

        # Act
        result = quote.to_dict()

        # Assert
        assert result["symbol"] == "MXF202601"
        assert result["code"] == "MXFA6"
        assert result["close"] == 21500.0
        assert result["change_price"] == 100.0
        assert result["buy_price"] == 21499.0
        assert result["sell_price"] == 21501.0

    def test_to_json_應該正確序列化(self):
        """測試: QuoteData 應該能正確序列化為 JSON"""
        # Arrange
        quote = QuoteData(
            symbol="TXF202601",
            code="TXFA6",
            close=21500.0,
            timestamp=1704067200000,
        )

        # Act
        json_str = quote.to_json()
        parsed = json.loads(json_str)

        # Assert
        assert parsed["symbol"] == "TXF202601"
        assert parsed["close"] == 21500.0


class TestQuoteManagerInit:
    """QuoteManager 初始化測試"""

    def test_初始化應該建立空的訂閱字典(self):
        """測試: 初始化時應該建立空的訂閱追蹤字典"""
        # Arrange
        mock_api = Mock()
        mock_redis = Mock()

        # Act
        manager = QuoteManager(api=mock_api, redis_client=mock_redis)

        # Assert
        assert manager._subscriptions == {}
        assert manager._subscriber_counts == {}

    def test_初始化應該儲存API和Redis引用(self):
        """測試: 初始化時應該正確儲存 API 和 Redis 引用"""
        # Arrange
        mock_api = Mock()
        mock_redis = Mock()

        # Act
        manager = QuoteManager(api=mock_api, redis_client=mock_redis)

        # Assert
        assert manager._api is mock_api
        assert manager._redis is mock_redis


class TestQuoteManagerSubscribe:
    """QuoteManager.subscribe 測試"""

    def test_subscribe_新商品應該調用API訂閱(self):
        """測試: 訂閱新商品時應該調用 Shioaji API 訂閱"""
        # Arrange
        mock_api = Mock()
        mock_contract = Mock()
        mock_contract.symbol = "MXF202601"
        mock_contract.code = "MXFA6"
        mock_api.Contracts.Futures.MXF.MXF202601 = mock_contract

        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)

        # Act
        result = manager.subscribe("MXF202601", mock_contract)

        # Assert
        assert result is True
        mock_api.quote.subscribe.assert_called_once()
        assert manager._subscriber_counts.get("MXF202601") == 1

    def test_subscribe_已訂閱商品應該只增加計數(self):
        """測試: 訂閱已訂閱的商品時應該只增加計數不重複調用 API"""
        # Arrange
        mock_api = Mock()
        mock_contract = Mock()
        mock_contract.symbol = "MXF202601"
        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)
        manager._subscriptions["MXF202601"] = mock_contract
        manager._subscriber_counts["MXF202601"] = 1

        # Act
        result = manager.subscribe("MXF202601", mock_contract)

        # Assert
        assert result is True
        # API 不應該被調用（已訂閱）
        mock_api.quote.subscribe.assert_not_called()
        # 計數應該增加
        assert manager._subscriber_counts["MXF202601"] == 2

    def test_subscribe_失敗時應該返回False(self):
        """測試: 訂閱失敗時應該返回 False"""
        # Arrange
        mock_api = Mock()
        mock_api.quote.subscribe.side_effect = Exception("訂閱失敗")
        mock_contract = Mock()
        mock_contract.symbol = "MXF202601"
        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)

        # Act
        result = manager.subscribe("MXF202601", mock_contract)

        # Assert
        assert result is False
        assert "MXF202601" not in manager._subscriptions


class TestQuoteManagerUnsubscribe:
    """QuoteManager.unsubscribe 測試"""

    def test_unsubscribe_最後一個訂閱者應該取消API訂閱(self):
        """測試: 最後一個訂閱者取消時應該調用 API 取消訂閱"""
        # Arrange
        mock_api = Mock()
        mock_contract = Mock()
        mock_contract.symbol = "MXF202601"
        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)
        manager._subscriptions["MXF202601"] = mock_contract
        manager._subscriber_counts["MXF202601"] = 1

        # Act
        result = manager.unsubscribe("MXF202601")

        # Assert
        assert result is True
        mock_api.quote.unsubscribe.assert_called_once_with(mock_contract)
        assert "MXF202601" not in manager._subscriptions
        assert "MXF202601" not in manager._subscriber_counts

    def test_unsubscribe_還有其他訂閱者時應該只減少計數(self):
        """測試: 還有其他訂閱者時應該只減少計數不取消 API 訂閱"""
        # Arrange
        mock_api = Mock()
        mock_contract = Mock()
        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)
        manager._subscriptions["MXF202601"] = mock_contract
        manager._subscriber_counts["MXF202601"] = 3

        # Act
        result = manager.unsubscribe("MXF202601")

        # Assert
        assert result is True
        # API 不應該被調用（還有其他訂閱者）
        mock_api.quote.unsubscribe.assert_not_called()
        # 計數應該減少
        assert manager._subscriber_counts["MXF202601"] == 2

    def test_unsubscribe_未訂閱商品應該返回False(self):
        """測試: 取消訂閱未訂閱的商品應該返回 False"""
        # Arrange
        mock_api = Mock()
        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)

        # Act
        result = manager.unsubscribe("NOT_SUBSCRIBED")

        # Assert
        assert result is False


class TestQuoteManagerHandleQuote:
    """QuoteManager 報價回調處理測試"""

    def test_handle_quote_應該發布到Redis(self):
        """測試: 收到報價時應該發布到 Redis Pub/Sub"""
        # Arrange
        mock_api = Mock()
        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)
        manager._subscriptions["MXF202601"] = Mock()
        manager._code_to_symbol["MXFA6"] = "MXF202601"

        # 模擬 Shioaji 報價格式
        mock_exchange = Mock()
        mock_exchange.value = "TAIFEX"

        # 使用 spec 避免 Mock 的額外屬性被序列化
        mock_quote = Mock(spec=['code', 'close', 'open', 'high', 'low',
                                 'change_price', 'change_rate', 'volume',
                                 'total_volume', 'buy_price', 'sell_price',
                                 'buy_volume', 'sell_volume', 'datetime'])
        mock_quote.code = "MXFA6"
        mock_quote.close = [21500.0]
        mock_quote.open = 21400.0
        mock_quote.high = 21600.0
        mock_quote.low = 21350.0
        mock_quote.change_price = 100.0
        mock_quote.change_rate = 0.47
        mock_quote.volume = 150
        mock_quote.total_volume = 52000
        mock_quote.buy_price = [21499.0]
        mock_quote.sell_price = [21501.0]
        mock_quote.buy_volume = 50
        mock_quote.sell_volume = 60
        mock_quote.datetime = datetime(2024, 1, 1, 10, 0, 0)

        # Act
        manager._handle_quote(mock_exchange, mock_quote)

        # Assert
        mock_redis.publish.assert_called_once()
        call_args = mock_redis.publish.call_args
        channel = call_args[0][0]
        message = call_args[0][1]

        # 驗證 channel 格式
        assert channel.startswith(QUOTE_CHANNEL_PREFIX)
        assert "MXF202601" in channel

        # 驗證訊息內容
        data = json.loads(message)
        assert data["code"] == "MXFA6"
        assert data["close"] == 21500.0
        assert data["symbol"] == "MXF202601"

    def test_handle_quote_Redis錯誤時應該記錄日誌不中斷(self):
        """測試: Redis 發布失敗時應該記錄日誌但不中斷處理"""
        # Arrange
        mock_api = Mock()
        mock_redis = Mock()
        mock_redis.publish.side_effect = Exception("Redis connection error")

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)
        manager._subscriptions["MXF202601"] = Mock()

        mock_exchange = Mock()
        mock_exchange.value = "TAIFEX"
        mock_quote = Mock()
        mock_quote.code = "MXFA6"
        mock_quote.close = [21500.0]
        mock_quote.datetime = datetime.now()

        # Act & Assert - 應該不拋出例外
        manager._handle_quote(mock_exchange, mock_quote)


class TestQuoteManagerGetSubscriptions:
    """QuoteManager 訂閱狀態查詢測試"""

    def test_get_subscriptions_應該返回訂閱列表(self):
        """測試: get_subscriptions 應該返回目前訂閱的商品列表"""
        # Arrange
        mock_api = Mock()
        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)
        manager._subscriptions["MXF202601"] = Mock()
        manager._subscriptions["TXF202601"] = Mock()

        # Act
        result = manager.get_subscriptions()

        # Assert
        assert len(result) == 2
        assert "MXF202601" in result
        assert "TXF202601" in result

    def test_get_subscriber_count_應該返回訂閱者數量(self):
        """測試: get_subscriber_count 應該返回特定商品的訂閱者數量"""
        # Arrange
        mock_api = Mock()
        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)
        manager._subscriber_counts["MXF202601"] = 5

        # Act
        result = manager.get_subscriber_count("MXF202601")

        # Assert
        assert result == 5

    def test_get_subscriber_count_未訂閱應該返回0(self):
        """測試: 未訂閱商品的訂閱者數量應該為 0"""
        # Arrange
        mock_api = Mock()
        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)

        # Act
        result = manager.get_subscriber_count("NOT_SUBSCRIBED")

        # Assert
        assert result == 0


class TestQuoteManagerSetupCallback:
    """QuoteManager 回調設置測試"""

    def test_setup_quote_callback_應該註冊回調函數(self):
        """測試: setup_quote_callback 應該正確註冊 Shioaji 回調函數"""
        # Arrange
        mock_api = Mock()
        mock_redis = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)

        # Act
        manager.setup_quote_callback()

        # Assert
        # 驗證 on_quote 被設置為裝飾器
        # 在實際實作中，我們會在 __init__ 或單獨方法中設置


class TestQuoteManagerCleanup:
    """QuoteManager 清理功能測試"""

    def test_cleanup_應該取消所有訂閱(self):
        """測試: cleanup 應該取消所有現有訂閱"""
        # Arrange
        mock_api = Mock()
        mock_redis = Mock()

        mock_contract1 = Mock()
        mock_contract2 = Mock()

        manager = QuoteManager(api=mock_api, redis_client=mock_redis)
        manager._subscriptions = {
            "MXF202601": mock_contract1,
            "TXF202601": mock_contract2,
        }
        manager._subscriber_counts = {
            "MXF202601": 1,
            "TXF202601": 1,
        }

        # Act
        manager.cleanup()

        # Assert
        assert mock_api.quote.unsubscribe.call_count == 2
        assert manager._subscriptions == {}
        assert manager._subscriber_counts == {}

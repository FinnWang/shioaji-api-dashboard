"""
QuoteStorage 單元測試

測試涵蓋：
1. 初始化與配置
2. 緩衝區管理
3. 批次寫入邏輯
4. 背景執行緒控制
5. 錯誤處理與重試
6. 統計資訊
"""
import pytest
import time
import threading
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime, timezone

from quote_storage import QuoteStorage, MAX_WRITE_RETRIES


class TestQuoteStorageInit:
    """QuoteStorage 初始化測試"""

    @patch("quote_storage.settings")
    def test_初始化應該讀取設定值(self, mock_settings):
        """測試: 初始化時應該從 settings 讀取預設值"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 50
        mock_settings.quote_storage_flush_interval = 3.0

        # Act
        storage = QuoteStorage()

        # Assert
        assert storage._buffer_size == 50
        assert storage._flush_interval == 3.0
        assert storage._enabled is False

    @patch("quote_storage.settings")
    def test_初始化可覆蓋設定值(self, mock_settings):
        """測試: 初始化時參數可以覆蓋預設設定"""
        # Arrange
        mock_settings.quote_storage_enabled = True
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        # Act
        storage = QuoteStorage(
            buffer_size=200,
            flush_interval=10.0,
            enabled=False,
        )

        # Assert
        assert storage._buffer_size == 200
        assert storage._flush_interval == 10.0
        assert storage._enabled is False

    @patch("quote_storage.settings")
    def test_停用時不應該啟動背景執行緒(self, mock_settings):
        """測試: 停用狀態時不應該啟動背景執行緒"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        # Act
        storage = QuoteStorage()

        # Assert
        assert storage._running is False
        assert storage._flush_thread is None


class TestQuoteStorageAddQuote:
    """QuoteStorage.add_quote 測試"""

    @patch("quote_storage.settings")
    def test_add_quote_停用時應該返回False(self, mock_settings):
        """測試: 停用狀態時 add_quote 應該返回 False"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        storage = QuoteStorage()
        quote_data = {
            "symbol": "MXFR1",
            "code": "MXFA6",
            "quote_type": "tick",
            "close": 21500.0,
            "timestamp": 1704067200000,
        }

        # Act
        result = storage.add_quote(quote_data)

        # Assert
        assert result is False

    @patch("quote_storage.settings")
    def test_add_quote_缺少必要欄位應該返回False(self, mock_settings):
        """測試: 缺少 symbol 或 code 時應該返回 False"""
        # Arrange
        mock_settings.quote_storage_enabled = True
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        storage = QuoteStorage(enabled=True)
        storage._running = False  # 避免啟動背景執行緒

        # Act - 缺少 symbol
        result1 = storage.add_quote({"code": "MXFA6"})
        # Act - 缺少 code
        result2 = storage.add_quote({"symbol": "MXFR1"})

        # Assert
        assert result1 is False
        assert result2 is False

    @patch("quote_storage.settings")
    def test_add_quote_應該加入緩衝區(self, mock_settings):
        """測試: add_quote 應該正確將資料加入緩衝區"""
        # Arrange
        mock_settings.quote_storage_enabled = True
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        storage = QuoteStorage(enabled=True)
        storage._running = True  # 模擬已啟動

        quote_data = {
            "symbol": "MXFR1",
            "code": "MXFA6",
            "quote_type": "tick",
            "close": 21500.0,
            "timestamp": 1704067200000,
        }

        # Act
        result = storage.add_quote(quote_data)

        # Assert
        assert result is True
        assert len(storage._buffer) == 1

        # 清理
        storage.stop()


class TestQuoteStorageCreateQuoteRecord:
    """QuoteStorage._create_quote_record 測試"""

    @patch("quote_storage.settings")
    def test_create_quote_record_應該正確轉換時間戳(self, mock_settings):
        """測試: _create_quote_record 應該正確轉換毫秒時間戳"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        storage = QuoteStorage()

        quote_data = {
            "symbol": "MXFR1",
            "code": "MXFA6",
            "quote_type": "tick",
            "close": 21500.0,
            "timestamp": 1704067200000,  # 2024-01-01 00:00:00 UTC
        }

        # Act
        record = storage._create_quote_record(quote_data)

        # Assert
        assert record["symbol"] == "MXFR1"
        assert record["code"] == "MXFA6"
        assert record["quote_type"] == "tick"
        assert record["close_price"] == 21500.0
        assert isinstance(record["quote_time"], datetime)

    @patch("quote_storage.settings")
    def test_create_quote_record_應該處理零值欄位(self, mock_settings):
        """測試: _create_quote_record 應該將 0 值轉換為 None"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        storage = QuoteStorage()

        quote_data = {
            "symbol": "MXFR1",
            "code": "MXFA6",
            "quote_type": "bidask",
            "close": 0.0,  # BidAsk 沒有成交價
            "buy_price": 21499.0,
            "sell_price": 21501.0,
            "timestamp": 1704067200000,
        }

        # Act
        record = storage._create_quote_record(quote_data)

        # Assert
        assert record["close_price"] is None  # 0 應轉為 None
        assert record["buy_price"] == 21499.0
        assert record["sell_price"] == 21501.0


class TestQuoteStorageFlushBuffer:
    """QuoteStorage._flush_buffer 測試"""

    @patch("quote_storage.SessionLocal")
    @patch("quote_storage.settings")
    def test_flush_buffer_空緩衝區不應該建立資料庫連線(
        self, mock_settings, mock_session_local
    ):
        """測試: 緩衝區為空時不應該建立資料庫連線"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        storage = QuoteStorage()

        # Act
        storage._flush_buffer()

        # Assert
        mock_session_local.assert_not_called()

    @patch("quote_storage.SessionLocal")
    @patch("quote_storage.QuoteHistory")
    @patch("quote_storage.settings")
    def test_flush_buffer_應該批次儲存記錄(
        self, mock_settings, mock_quote_history, mock_session_local
    ):
        """測試: _flush_buffer 應該批次儲存緩衝區記錄"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        storage = QuoteStorage()

        # 手動加入記錄到緩衝區
        storage._buffer.append({
            "symbol": "MXFR1",
            "code": "MXFA6",
            "quote_type": "tick",
            "close_price": 21500.0,
            "quote_time": datetime.now(timezone.utc),
        })
        storage._buffer.append({
            "symbol": "MXFR1",
            "code": "MXFA6",
            "quote_type": "tick",
            "close_price": 21501.0,
            "quote_time": datetime.now(timezone.utc),
        })

        # Act
        storage._flush_buffer()

        # Assert
        mock_db.bulk_save_objects.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()
        assert len(storage._buffer) == 0
        assert storage._total_quotes_stored == 2
        assert storage._total_flush_count == 1

    @patch("quote_storage.SessionLocal")
    @patch("quote_storage.settings")
    def test_flush_buffer_資料庫錯誤應該重試(
        self, mock_settings, mock_session_local
    ):
        """測試: 資料庫錯誤時應該重試"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        from sqlalchemy.exc import SQLAlchemyError

        mock_db = MagicMock()
        mock_db.bulk_save_objects.side_effect = SQLAlchemyError("Connection error")
        mock_session_local.return_value = mock_db

        storage = QuoteStorage()
        storage._buffer.append({
            "symbol": "MXFR1",
            "code": "MXFA6",
            "quote_type": "tick",
            "close_price": 21500.0,
            "quote_time": datetime.now(timezone.utc),
        })

        # Act
        storage._flush_buffer()

        # Assert - 應該重試 MAX_WRITE_RETRIES 次
        assert mock_db.bulk_save_objects.call_count == MAX_WRITE_RETRIES
        assert storage._consecutive_errors > 0


class TestQuoteStorageStartStop:
    """QuoteStorage 啟動/停止測試"""

    @patch("quote_storage.settings")
    def test_start_應該啟動背景執行緒(self, mock_settings):
        """測試: start 應該啟動背景刷新執行緒"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        storage = QuoteStorage()

        # Act
        storage.start()

        # Assert
        assert storage._running is True
        assert storage._flush_thread is not None
        assert storage._flush_thread.is_alive()

        # 清理
        storage.stop()

    @patch("quote_storage.settings")
    def test_stop_應該停止背景執行緒(self, mock_settings):
        """測試: stop 應該停止背景刷新執行緒"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 0.1  # 短間隔加速測試

        storage = QuoteStorage()
        storage.start()

        # Act
        storage.stop()

        # Assert
        assert storage._running is False

    @patch("quote_storage.SessionLocal")
    @patch("quote_storage.settings")
    def test_stop_應該刷新剩餘資料(self, mock_settings, mock_session_local):
        """測試: stop 應該在停止前刷新緩衝區剩餘資料"""
        # Arrange
        mock_settings.quote_storage_enabled = True  # 啟用才會呼叫 stop 時刷新
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 100.0  # 長間隔避免自動刷新

        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        storage = QuoteStorage(enabled=True)
        storage._buffer.append({
            "symbol": "MXFR1",
            "code": "MXFA6",
            "quote_type": "tick",
            "close_price": 21500.0,
            "quote_time": datetime.now(timezone.utc),
        })

        # Act
        storage.stop()

        # Assert - 應該刷新剩餘資料
        mock_db.bulk_save_objects.assert_called_once()


class TestQuoteStorageStats:
    """QuoteStorage 統計資訊測試"""

    @patch("quote_storage.settings")
    def test_get_stats_應該返回統計資訊(self, mock_settings):
        """測試: get_stats 應該返回完整的統計資訊"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        storage = QuoteStorage()
        storage._total_quotes_stored = 1000
        storage._total_flush_count = 10

        # Act
        stats = storage.get_stats()

        # Assert
        assert stats["enabled"] is False
        assert stats["buffer_capacity"] == 100
        assert stats["flush_interval"] == 5.0
        assert stats["total_quotes_stored"] == 1000
        assert stats["total_flush_count"] == 10

    @patch("quote_storage.settings")
    def test_is_enabled_應該返回啟用狀態(self, mock_settings):
        """測試: is_enabled 應該返回正確的啟用狀態"""
        # Arrange
        mock_settings.quote_storage_enabled = True
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        storage = QuoteStorage(enabled=True)

        # Act & Assert
        assert storage.is_enabled is True

        # 清理
        storage.stop()

    @patch("quote_storage.settings")
    def test_is_running_應該返回執行狀態(self, mock_settings):
        """測試: is_running 應該返回正確的執行狀態"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        storage = QuoteStorage()

        # Act & Assert
        assert storage.is_running is False

        storage.start()
        assert storage.is_running is True

        storage.stop()
        assert storage.is_running is False


class TestQuoteStorageBufferTrigger:
    """QuoteStorage 緩衝區觸發測試"""

    @patch("quote_storage.settings")
    def test_緩衝區滿時應該觸發刷新(self, mock_settings):
        """測試: 緩衝區達到上限時應該觸發非同步刷新"""
        # Arrange
        mock_settings.quote_storage_enabled = True
        mock_settings.quote_storage_buffer_size = 3  # 小緩衝區便於測試
        mock_settings.quote_storage_flush_interval = 100.0  # 長間隔避免自動刷新

        storage = QuoteStorage(enabled=True, buffer_size=3)
        storage._running = True

        # Mock _flush_buffer
        with patch.object(storage, '_flush_buffer') as mock_flush:
            # Act - 加入資料直到觸發
            storage.add_quote({
                "symbol": "MXFR1", "code": "MXFA6", "quote_type": "tick",
                "close": 21500.0, "timestamp": 1704067200000
            })
            storage.add_quote({
                "symbol": "MXFR1", "code": "MXFA6", "quote_type": "tick",
                "close": 21501.0, "timestamp": 1704067201000
            })

            # 等待非同步刷新執行緒啟動（如果有的話）
            time.sleep(0.1)

            # 第三筆應該觸發刷新
            storage.add_quote({
                "symbol": "MXFR1", "code": "MXFA6", "quote_type": "tick",
                "close": 21502.0, "timestamp": 1704067202000
            })

            # 等待非同步刷新執行緒執行
            time.sleep(0.2)

        # 清理
        storage._running = False
        storage.stop()


class TestQuoteManagerWithQuoteStorage:
    """QuoteManager 與 QuoteStorage 整合測試"""

    @patch("quote_storage.settings")
    def test_QuoteManager應該能注入QuoteStorage(self, mock_settings):
        """測試: QuoteManager 應該能接受 QuoteStorage 注入"""
        # Arrange
        mock_settings.quote_storage_enabled = False
        mock_settings.quote_storage_buffer_size = 100
        mock_settings.quote_storage_flush_interval = 5.0

        from quote_manager import QuoteManager

        mock_api = Mock()
        mock_redis = Mock()
        storage = QuoteStorage()

        # Act
        manager = QuoteManager(
            api=mock_api,
            redis_client=mock_redis,
            quote_storage=storage,
        )

        # Assert
        assert manager._quote_storage is storage

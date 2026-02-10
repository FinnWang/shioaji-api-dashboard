"""
StrategyEventStorage 單元測試

測試涵蓋：
1. 緩衝區管理
2. 批次寫入邏輯
3. 交易回合配對（entry → exit）
4. 停損事件處理
5. 損益計算
"""
import pytest
import time
from unittest.mock import Mock, MagicMock, patch, call
from datetime import datetime, timezone

from strategy_event_storage import StrategyEventStorage, MAX_WRITE_RETRIES


def _make_event(event_type, symbol="MXFR1", data=None, timestamp_ms=None):
    """輔助函數：建立策略事件"""
    return {
        "event_type": event_type,
        "symbol": symbol,
        "timestamp": timestamp_ms or int(time.time() * 1000),
        "data": data or {},
    }


class TestStrategyEventStorageInit:
    """初始化測試"""

    def test_初始化應該使用預設參數(self):
        storage = StrategyEventStorage(enabled=False)

        assert storage._buffer_size == 20
        assert storage._flush_interval == 2.0
        assert storage._enabled is False
        assert storage._total_events_stored == 0
        assert storage._total_trades_created == 0

    def test_初始化可覆蓋參數(self):
        storage = StrategyEventStorage(
            buffer_size=50,
            flush_interval=5.0,
            enabled=False,
        )

        assert storage._buffer_size == 50
        assert storage._flush_interval == 5.0

    def test_停用時不啟動背景執行緒(self):
        storage = StrategyEventStorage(enabled=False)

        assert storage._running is False
        assert storage._flush_thread is None


class TestAddEvent:
    """add_event 測試"""

    def test_add_event_應該加入緩衝區(self):
        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)
        # 手動停止背景執行緒避免干擾
        storage._running = False

        event = _make_event("entry", data={"direction": "long", "price": 21000})
        result = storage.add_event(event)

        assert result is True
        assert len(storage._buffer) == 1

    def test_add_event_停用時應該返回False(self):
        storage = StrategyEventStorage(enabled=False)

        event = _make_event("entry")
        result = storage.add_event(event)

        assert result is False
        assert len(storage._buffer) == 0

    def test_add_event_缺少必要欄位應該返回False(self):
        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)
        storage._running = False

        # 缺少 event_type
        result = storage.add_event({"symbol": "MXFR1"})
        assert result is False

        # 缺少 symbol
        result = storage.add_event({"event_type": "entry"})
        assert result is False

    def test_add_event_多筆應該正確累計(self):
        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)
        storage._running = False

        for i in range(5):
            storage.add_event(_make_event("signal", data={"action": "Buy"}))

        assert len(storage._buffer) == 5


class TestFlushBuffer:
    """_flush_buffer 與 _process_events 測試"""

    @patch("strategy_event_storage.SessionLocal")
    def test_flush_buffer_應該批次寫入資料庫(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)
        storage._running = False

        # 加入事件
        storage.add_event(_make_event("signal", data={"action": "Buy", "price": 21000}))
        storage.add_event(_make_event("signal", data={"action": "Sell", "price": 20500}))

        # 執行刷新
        storage._flush_buffer()

        # 應該呼叫 commit
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()
        assert storage._total_events_stored == 2
        assert len(storage._buffer) == 0

    @patch("strategy_event_storage.SessionLocal")
    def test_entry_事件應該建立strategy_trade(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)
        storage._running = False

        event = _make_event("entry", data={
            "direction": "long",
            "price": 21000,
            "quantity": 2,
        })
        storage.add_event(event)
        storage._flush_buffer()

        # 應該呼叫 db.add 兩次：一次 StrategyEvent，一次 StrategyTrade
        assert mock_db.add.call_count == 2
        assert storage._total_trades_created == 1

    @patch("strategy_event_storage.SessionLocal")
    def test_exit_事件應該關閉對應的strategy_trade(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        # 模擬找到 open trade
        mock_open_trade = MagicMock()
        mock_open_trade.direction = "long"
        mock_open_trade.entry_price = 21000.0
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_open_trade

        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)
        storage._running = False

        event = _make_event("exit", data={
            "price": 21050,
            "pnl": 50.0,
            "direction": "long",
        })
        storage.add_event(event)
        storage._flush_buffer()

        # trade 應該被關閉
        assert mock_open_trade.status == "closed"
        assert mock_open_trade.exit_price == 21050
        assert mock_open_trade.exit_reason == "signal"
        assert storage._total_trades_closed == 1

    @patch("strategy_event_storage.SessionLocal")
    def test_stop_loss_事件應該記錄停損原因(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        mock_open_trade = MagicMock()
        mock_open_trade.direction = "long"
        mock_open_trade.entry_price = 21000.0
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_open_trade

        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)
        storage._running = False

        event = _make_event("stop_loss", data={
            "price": 20950,
            "reason": "trailing",
            "direction": "long",
        })
        storage.add_event(event)
        storage._flush_buffer()

        # 應該記錄停損原因
        assert mock_open_trade.exit_reason == "trailing"
        assert mock_open_trade.status == "closed"

    @patch("strategy_event_storage.SessionLocal")
    def test_交易回合配對應該正確計算pnl_做多(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        mock_open_trade = MagicMock()
        mock_open_trade.direction = "long"
        mock_open_trade.entry_price = 21000.0
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_open_trade

        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)
        storage._running = False

        event = _make_event("exit", data={"price": 21050, "direction": "long"})
        storage.add_event(event)
        storage._flush_buffer()

        # 做多: exit - entry = 21050 - 21000 = 50
        assert mock_open_trade.pnl == 50.0

    @patch("strategy_event_storage.SessionLocal")
    def test_交易回合配對應該正確計算pnl_做空(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        mock_open_trade = MagicMock()
        mock_open_trade.direction = "short"
        mock_open_trade.entry_price = 21000.0
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = mock_open_trade

        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)
        storage._running = False

        event = _make_event("exit", data={"price": 20950, "direction": "short"})
        storage.add_event(event)
        storage._flush_buffer()

        # 做空: entry - exit = 21000 - 20950 = 50
        assert mock_open_trade.pnl == 50.0

    @patch("strategy_event_storage.SessionLocal")
    def test_exit_無對應open_trade時應該記錄警告(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db
        mock_db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)
        storage._running = False

        event = _make_event("exit", data={"price": 21050})
        storage.add_event(event)
        storage._flush_buffer()

        # 不應該有 trade 被關閉
        assert storage._total_trades_closed == 0


class TestGetStats:
    """統計資訊測試"""

    def test_get_stats_應該返回正確的統計資訊(self):
        storage = StrategyEventStorage(enabled=False)

        stats = storage.get_stats()

        assert stats["enabled"] is False
        assert stats["running"] is False
        assert stats["buffer_size"] == 0
        assert stats["buffer_capacity"] == 20
        assert stats["total_events_stored"] == 0
        assert stats["total_trades_created"] == 0
        assert stats["total_trades_closed"] == 0


class TestStartStop:
    """啟動/停止測試"""

    def test_start_應該啟動背景執行緒(self):
        storage = StrategyEventStorage(enabled=False)
        storage._enabled = True

        storage.start()

        assert storage._running is True
        assert storage._flush_thread is not None
        assert storage._flush_thread.is_alive() is True

        # 清理
        storage.stop()

    @patch("strategy_event_storage.SessionLocal")
    def test_stop_應該刷新剩餘緩衝區(self, mock_session_cls):
        mock_db = MagicMock()
        mock_session_cls.return_value = mock_db

        storage = StrategyEventStorage(enabled=True, buffer_size=100, flush_interval=999)

        # 加入事件
        storage.add_event(_make_event("signal", data={"action": "Buy"}))

        # 停止
        storage.stop()

        # 應該有刷新
        mock_db.commit.assert_called()

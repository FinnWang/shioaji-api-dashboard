"""
StrategyWorker 單元測試

測試涵蓋：
1. _place_exit 的 position_direction 傳值修正（Bug Fix 1）
2. 平倉假成功檢測（Bug Fix 2）
3. _save_order_history 委託紀錄寫入（Bug Fix 3）
4. _place_entry 整合 OrderHistory
"""
import pytest
from unittest.mock import MagicMock, patch, call

from strategy_worker import StrategyWorker
from trading_queue import TradingResponse


def _create_worker():
    """建立測試用 StrategyWorker（跳過 Redis 連線）"""
    with patch("strategy_worker.redis.from_url") as mock_redis, \
         patch("strategy_worker.StrategyEventStorage") as mock_storage:
        mock_redis.return_value = MagicMock()
        mock_storage_instance = MagicMock()
        mock_storage.return_value = mock_storage_instance

        worker = StrategyWorker()
        worker._trading_client = MagicMock()
        worker._event_storage = mock_storage_instance
        return worker


def _make_response(success=True, data=None, error=None):
    """建立 TradingResponse（含必要的 request_id）"""
    return TradingResponse(
        request_id="test-req-001",
        success=success,
        data=data,
        error=error,
    )


class TestPlaceExitPositionDirection:
    """測試 _place_exit 的 position_direction 傳值"""

    def test_做多平倉應傳送Buy(self):
        worker = _create_worker()
        worker._position_manager.open_position("long", 21000.0)

        response = _make_response(data={"order_id": "abc123", "code": "MXFA6"})
        worker._trading_client.place_exit_order.return_value = response

        with patch.object(worker, "_save_order_history"):
            worker._place_exit(21050.0)

        worker._trading_client.place_exit_order.assert_called_once()
        call_kwargs = worker._trading_client.place_exit_order.call_args
        assert call_kwargs.kwargs.get("position_direction") == "Buy"

    def test_做空平倉應傳送Sell(self):
        worker = _create_worker()
        worker._position_manager.open_position("short", 21000.0)

        response = _make_response(data={"order_id": "abc123", "code": "MXFA6"})
        worker._trading_client.place_exit_order.return_value = response

        with patch.object(worker, "_save_order_history"):
            worker._place_exit(20950.0)

        worker._trading_client.place_exit_order.assert_called_once()
        call_kwargs = worker._trading_client.place_exit_order.call_args
        assert call_kwargs.kwargs.get("position_direction") == "Sell"

    def test_空倉時不應下單(self):
        worker = _create_worker()
        # 預設是 flat，不做任何操作

        worker._place_exit(21000.0)

        worker._trading_client.place_exit_order.assert_not_called()


class TestPlaceExitFalseSuccess:
    """測試平倉假成功檢測"""

    def test_order_id為None且有message應偵測為假成功(self):
        worker = _create_worker()
        worker._position_manager.open_position("long", 21000.0)

        response = _make_response(data={"order_id": None, "message": "No position to exit"})
        worker._trading_client.place_exit_order.return_value = response

        worker._place_exit(21050.0)

        # 假成功：持倉應被清除
        assert worker._position_manager.is_flat

    def test_假成功時清除pending_reverse(self):
        worker = _create_worker()
        worker._position_manager.open_position("long", 21000.0)
        worker._pending_reverse = "short"  # 模擬反轉等待

        response = _make_response(data={"order_id": None, "message": "No position to exit"})
        worker._trading_client.place_exit_order.return_value = response

        worker._place_exit(21050.0)

        assert worker._pending_reverse is None

    def test_假成功不發布exit事件(self):
        worker = _create_worker()
        worker._position_manager.open_position("long", 21000.0)

        response = _make_response(data={"order_id": None, "message": "No position to exit"})
        worker._trading_client.place_exit_order.return_value = response

        with patch.object(worker, "_publish_event") as mock_publish:
            worker._place_exit(21050.0)

            # 不應有 exit 事件
            exit_calls = [
                c for c in mock_publish.call_args_list
                if c.args[0] == "exit"
            ]
            assert len(exit_calls) == 0

    def test_假成功不呼叫risk_manager_on_exit(self):
        worker = _create_worker()
        worker._position_manager.open_position("long", 21000.0)
        worker._risk_manager.on_entry(21000.0, "long")

        response = _make_response(data={"order_id": None, "message": "No position to exit"})
        worker._trading_client.place_exit_order.return_value = response

        with patch.object(worker._risk_manager, "on_exit") as mock_on_exit:
            worker._place_exit(21050.0)
            mock_on_exit.assert_not_called()

    def test_真實成功正常執行(self):
        worker = _create_worker()
        worker._position_manager.open_position("long", 21000.0)
        worker._risk_manager.on_entry(21000.0, "long")

        response = _make_response(data={"order_id": "abc123", "code": "MXFA6"})
        worker._trading_client.place_exit_order.return_value = response

        with patch.object(worker, "_publish_event") as mock_publish, \
             patch.object(worker, "_save_order_history"):
            worker._place_exit(21050.0)

            # 真實成功：應發布 exit 事件
            exit_calls = [
                c for c in mock_publish.call_args_list
                if c.args[0] == "exit"
            ]
            assert len(exit_calls) == 1

            # 真實成功：持倉應被清除
            assert worker._position_manager.is_flat


class TestSaveOrderHistory:
    """測試 _save_order_history 委託紀錄寫入"""

    @patch("strategy_worker.SessionLocal")
    def test_進場寫入OrderHistory(self, mock_session_local):
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        worker = _create_worker()
        result_data = {"order_id": "abc123", "code": "MXFA6", "seqno": "1", "ordno": "O1"}

        worker._save_order_history("long_entry", result_data, 21000.0)

        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.close.assert_called_once()

        # 驗證 OrderHistory 欄位
        order = mock_db.add.call_args.args[0]
        assert order.symbol == worker.settings.symbol
        assert order.action == "long_entry"
        assert order.order_id == "abc123"
        assert order.code == "MXFA6"
        assert order.simulation == 1  # 預設模擬模式

    @patch("strategy_worker.SessionLocal")
    def test_出場寫入OrderHistory(self, mock_session_local):
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db

        worker = _create_worker()
        result_data = {"order_id": "def456", "code": "MXFA6"}

        worker._save_order_history("short_exit", result_data, 20900.0)

        mock_db.add.assert_called_once()
        order = mock_db.add.call_args.args[0]
        assert order.action == "short_exit"
        assert order.order_id == "def456"

    @patch("strategy_worker.SessionLocal")
    def test_DB錯誤不拋出例外(self, mock_session_local):
        mock_db = MagicMock()
        mock_db.commit.side_effect = Exception("DB connection lost")
        mock_session_local.return_value = mock_db

        worker = _create_worker()

        # 不應拋出例外
        worker._save_order_history("long_entry", {"order_id": "abc"}, 21000.0)

        mock_db.rollback.assert_called_once()
        mock_db.close.assert_called_once()

    @patch("strategy_worker.SessionLocal")
    def test_SessionLocal建立失敗不拋出例外(self, mock_session_local):
        mock_session_local.side_effect = Exception("Cannot connect to DB")

        worker = _create_worker()

        # 不應拋出例外
        worker._save_order_history("long_entry", {"order_id": "abc"}, 21000.0)


class TestPlaceEntryOrderHistory:
    """測試 _place_entry 整合 OrderHistory"""

    def test_進場成功呼叫save(self):
        worker = _create_worker()
        worker._risk_manager.reset_daily()  # 確保風控允許交易

        response = _make_response(data={"order_id": "abc123", "code": "MXFA6"})
        worker._trading_client.place_entry_order.return_value = response

        with patch.object(worker, "_save_order_history") as mock_save, \
             patch.object(worker, "_publish_event"):
            worker._place_entry("long", 21000.0)

            mock_save.assert_called_once_with(
                "long_entry",
                {"order_id": "abc123", "code": "MXFA6"},
                21000.0,
            )

    def test_進場失敗不呼叫save(self):
        worker = _create_worker()

        response = _make_response(success=False, error="Order rejected")
        worker._trading_client.place_entry_order.return_value = response

        with patch.object(worker, "_save_order_history") as mock_save:
            worker._place_entry("long", 21000.0)

            mock_save.assert_not_called()

    def test_風控拒絕不呼叫save(self):
        worker = _create_worker()
        # 設定風控拒絕：直接設定 trading_halted
        worker._risk_manager.state.trading_halted = True
        worker._risk_manager.state.halt_reason = "daily_loss_limit"

        with patch.object(worker, "_save_order_history") as mock_save:
            worker._place_entry("long", 21000.0)

            mock_save.assert_not_called()
            worker._trading_client.place_entry_order.assert_not_called()

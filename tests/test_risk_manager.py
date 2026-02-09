"""
RiskManager 單元測試

測試涵蓋：
1. 固定停損（多/空）
2. 追蹤停損（只往有利方向移動）
3. 每日虧損限制
4. 每日交易次數上限
5. 狀態序列化/反序列化
6. 每日重設
"""
import pytest

from risk_manager import RiskManager, RiskState, StopReason


class TestRiskState:
    """RiskState 序列化測試"""

    def test_序列化與反序列化應一致(self):
        """測試: RiskState 應能正確序列化與反序列化"""
        state = RiskState(
            entry_price=21000.0,
            position_direction="long",
            stop_loss_price=20950.0,
            trailing_stop_price=20970.0,
            best_price=21050.0,
            daily_pnl=-30.0,
            daily_trade_count=3,
        )

        json_str = state.to_json()
        restored = RiskState.from_json(json_str)

        assert restored.entry_price == 21000.0
        assert restored.position_direction == "long"
        assert restored.stop_loss_price == 20950.0
        assert restored.trailing_stop_price == 20970.0
        assert restored.best_price == 21050.0
        assert restored.daily_pnl == -30.0
        assert restored.daily_trade_count == 3


class TestRiskManagerFixedStopLoss:
    """固定停損測試"""

    def test_多單固定停損應在進場價減50點(self):
        """測試: 多單固定停損 = 進場價 - 50"""
        rm = RiskManager(stop_loss_points=50)
        rm.on_entry(21000.0, "long")

        assert rm.state.stop_loss_price == 20950.0

    def test_空單固定停損應在進場價加50點(self):
        """測試: 空單固定停損 = 進場價 + 50"""
        rm = RiskManager(stop_loss_points=50)
        rm.on_entry(21000.0, "short")

        assert rm.state.stop_loss_price == 21050.0

    def test_多單觸及固定停損應返回原因(self):
        """測試: 多單價格跌破固定停損線應觸發"""
        # 使用追蹤停損 > 固定停損，確保只測試固定停損
        rm = RiskManager(stop_loss_points=50, trailing_stop_points=60)
        rm.on_entry(21000.0, "long")

        # 未觸及（固定停損在 20950）
        assert rm.check_stop_loss(20960.0) is None

        # 觸及固定停損
        reason = rm.check_stop_loss(20950.0)
        assert reason == StopReason.FIXED_STOP_LOSS

    def test_空單觸及固定停損應返回原因(self):
        """測試: 空單價格漲破固定停損線應觸發"""
        # 使用追蹤停損 > 固定停損，確保只測試固定停損
        rm = RiskManager(stop_loss_points=50, trailing_stop_points=60)
        rm.on_entry(21000.0, "short")

        # 未觸及（固定停損在 21050）
        assert rm.check_stop_loss(21040.0) is None

        # 觸及固定停損
        reason = rm.check_stop_loss(21050.0)
        assert reason == StopReason.FIXED_STOP_LOSS


class TestRiskManagerTrailingStop:
    """追蹤停損測試"""

    def test_多單初始追蹤停損應在進場價減30點(self):
        """測試: 多單初始追蹤停損 = 進場價 - 30"""
        rm = RiskManager(trailing_stop_points=30)
        rm.on_entry(21000.0, "long")

        assert rm.state.trailing_stop_price == 20970.0

    def test_多單獲利時追蹤停損應上移(self):
        """測試: 多單價格創新高時，追蹤停損應跟隨上移"""
        rm = RiskManager(stop_loss_points=50, trailing_stop_points=30)
        rm.on_entry(21000.0, "long")

        # 價格上漲到 21100，追蹤停損應上移到 21070
        rm.check_stop_loss(21100.0)
        assert rm.state.trailing_stop_price == 21070.0

        # 價格繼續上漲到 21200，追蹤停損應上移到 21170
        rm.check_stop_loss(21200.0)
        assert rm.state.trailing_stop_price == 21170.0

    def test_多單回檔時追蹤停損不應下移(self):
        """測試: 多單價格回檔時，追蹤停損不應下移"""
        rm = RiskManager(stop_loss_points=50, trailing_stop_points=30)
        rm.on_entry(21000.0, "long")

        # 上漲到 21100
        rm.check_stop_loss(21100.0)
        trailing_after_up = rm.state.trailing_stop_price

        # 回檔到 21080（未觸及停損）
        rm.check_stop_loss(21080.0)
        assert rm.state.trailing_stop_price == trailing_after_up

    def test_空單獲利時追蹤停損應下移(self):
        """測試: 空單價格創新低時，追蹤停損應跟隨下移"""
        rm = RiskManager(stop_loss_points=50, trailing_stop_points=30)
        rm.on_entry(21000.0, "short")

        # 價格下跌到 20900，追蹤停損應下移到 20930
        rm.check_stop_loss(20900.0)
        assert rm.state.trailing_stop_price == 20930.0

    def test_多單觸及追蹤停損應返回原因(self):
        """測試: 多單價格跌破追蹤停損線應觸發"""
        rm = RiskManager(stop_loss_points=50, trailing_stop_points=30)
        rm.on_entry(21000.0, "long")

        # 上漲到 21100
        rm.check_stop_loss(21100.0)
        # 追蹤停損在 21070

        # 回檔觸及追蹤停損
        reason = rm.check_stop_loss(21070.0)
        assert reason == StopReason.TRAILING_STOP

    def test_空單觸及追蹤停損應返回原因(self):
        """測試: 空單價格漲破追蹤停損線應觸發"""
        rm = RiskManager(stop_loss_points=50, trailing_stop_points=30)
        rm.on_entry(21000.0, "short")

        # 下跌到 20900
        rm.check_stop_loss(20900.0)
        # 追蹤停損在 20930

        # 反彈觸及追蹤停損
        reason = rm.check_stop_loss(20930.0)
        assert reason == StopReason.TRAILING_STOP


class TestRiskManagerDailyLimits:
    """每日限制測試"""

    def test_每日虧損達上限應停止交易(self):
        """測試: 累計虧損達 200 點時應停止交易"""
        rm = RiskManager(
            stop_loss_points=50,
            trailing_stop_points=30,
            daily_max_loss_points=200,
        )

        # 第一筆虧損 100 點
        rm.on_entry(21000.0, "long")
        rm.on_exit(20900.0)
        assert rm.state.trading_halted is False

        # 第二筆虧損 100 點，累計 -200
        rm.on_entry(21000.0, "long")
        rm.on_exit(20900.0)
        assert rm.state.trading_halted is True
        assert rm.state.halt_reason == StopReason.DAILY_LOSS_LIMIT.value

    def test_虧損未達上限應允許繼續交易(self):
        """測試: 累計虧損未達上限時應允許交易"""
        rm = RiskManager(daily_max_loss_points=200)

        rm.on_entry(21000.0, "long")
        rm.on_exit(20950.0)  # 虧 50 點

        can, _ = rm.can_trade()
        assert can is True

    def test_每日交易次數達上限應停止交易(self):
        """測試: 交易次數達上限時應停止交易"""
        rm = RiskManager(daily_max_trades=2)

        rm.on_entry(21000.0, "long")
        rm.on_exit(21010.0)
        rm.on_entry(21000.0, "short")
        rm.on_exit(20990.0)

        can, reason = rm.can_trade()
        assert can is False
        assert "上限" in reason

    def test_can_trade交易已停止時應返回False(self):
        """測試: trading_halted 為 True 時 can_trade 應返回 False"""
        rm = RiskManager()
        rm.state.trading_halted = True
        rm.state.halt_reason = "test"

        can, _ = rm.can_trade()
        assert can is False


class TestRiskManagerOnExit:
    """平倉損益計算測試"""

    def test_多單獲利應正確計算(self):
        """測試: 多單獲利 = 出場價 - 進場價"""
        rm = RiskManager()
        rm.on_entry(21000.0, "long")
        pnl = rm.on_exit(21050.0)

        assert pnl == 50.0
        assert rm.state.daily_pnl == 50.0

    def test_空單獲利應正確計算(self):
        """測試: 空單獲利 = 進場價 - 出場價"""
        rm = RiskManager()
        rm.on_entry(21000.0, "short")
        pnl = rm.on_exit(20950.0)

        assert pnl == 50.0
        assert rm.state.daily_pnl == 50.0

    def test_平倉後應重設持倉狀態(self):
        """測試: 平倉後持倉相關狀態應重設"""
        rm = RiskManager()
        rm.on_entry(21000.0, "long")
        rm.on_exit(21050.0)

        assert rm.state.position_direction == "flat"
        assert rm.state.entry_price == 0.0
        assert rm.state.stop_loss_price == 0.0


class TestRiskManagerReset:
    """每日重設測試"""

    def test_reset_daily應清除所有每日統計(self):
        """測試: reset_daily 應重設每日統計"""
        rm = RiskManager()
        rm.state.daily_pnl = -150.0
        rm.state.daily_trade_count = 5
        rm.state.trading_halted = True
        rm.state.halt_reason = "test"

        rm.reset_daily()

        assert rm.state.daily_pnl == 0.0
        assert rm.state.daily_trade_count == 0
        assert rm.state.trading_halted is False
        assert rm.state.halt_reason == ""


class TestRiskManagerRestore:
    """狀態恢復測試"""

    def test_restore_state應正確恢復狀態(self):
        """測試: restore_state 應能從 RiskState 恢復"""
        rm = RiskManager()
        state = RiskState(
            entry_price=21000.0,
            position_direction="long",
            daily_pnl=-80.0,
            daily_trade_count=4,
        )

        rm.restore_state(state)

        assert rm.state.entry_price == 21000.0
        assert rm.state.daily_pnl == -80.0

    def test_空倉時check_stop_loss應返回None(self):
        """測試: 無持倉時不應觸發停損"""
        rm = RiskManager()
        assert rm.check_stop_loss(21000.0) is None
